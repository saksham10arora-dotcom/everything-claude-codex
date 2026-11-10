"""Runs one duo session: both agents, the message flow between them, the user's voice, cards and phases."""
import asyncio
import os
import re
import time
from dataclasses import dataclass

from duo import context
from duo.policy import classify

NAMES = {"claude": "Claude", "codex": "Codex"}
OTHER = {"claude": "codex", "codex": "claude"}
MENTION = re.compile(r"^\s*((?:@(?:claude|codex)\b[\s,]*)+)(.*)$", re.I | re.S)
READY = re.compile(r"\[\[READY:\s*(plan|done)\s*\]\]", re.I)


@dataclass
class Limits:
    hours: float = 2.0
    max_turns: int = 400
    circle_after: int = 8
    idle_delay: float = 3.0
    max_nudges: int = 3


class Orchestrator:
    def __init__(self, workdir, run_dir, agents, log, ctx, user, limits=None, brief_fn=None, report_fn=None):
        self.workdir, self.run_dir, self.agents, self.log, self.ctx, self.user = workdir, run_dir, agents, log, ctx, user
        self.limits = limits or Limits()
        self.brief_fn = brief_fn or context.brief
        self.report_fn = report_fn
        self.phase = "plan"
        self.status = "running"
        self.ready = {n: None for n in agents}
        self.cards = {}  # id -> {"future", "card", ...}
        self.activity = {n: [] for n in agents}
        self.outbox = {n: asyncio.Queue() for n in agents}
        self.nudges = 0
        self.turns = 0
        self.started_at = time.time()
        self.loop = None
        self._finished = None
        self._idle_task = None
        self._card_n = 0
        self._tasks = []
        for n, a in agents.items():
            a.on_event = lambda kind, data, n=n: self._on_event(n, kind, data)
            a.on_approval = self._approval
            a.on_turn_end = lambda n=n: self._turn_end(n)
            a.on_exit = lambda code, n=n: self._on_exit(n, code)

    # ------------------------------------------------------------------ run
    async def run(self, goal):
        self.loop = asyncio.get_running_loop()
        self._finished = self.loop.create_future()
        self.goal = goal
        self.log.add("duo", "status", status="running", phase="plan", goal=goal)
        for n in self.agents:
            self._tasks.append(asyncio.ensure_future(self._sender(n)))
        await asyncio.gather(*(self._start(n) for n in self.agents))
        try:
            return await self._finished
        finally:
            for t in self._tasks:
                t.cancel()

    async def _start(self, n):
        other = NAMES[OTHER[n]]
        brief = self.brief_fn(NAMES[n], other, self.goal, self.user, self.run_dir)
        first = (f"[duo] The run has started. Goal: {self.goal}\n"
                 f"Start by reading the project and planning with {other}. The plan goes in "
                 f"{os.path.join(self.run_dir, 'plan.md')}.")
        self.agents[n].busy = True
        await self.agents[n].start(brief, first)

    async def _sender(self, n):
        while True:
            text = await self.outbox[n].get()
            try:
                await self.agents[n].send(text)
            except Exception as e:  # a dead agent is handled by on_exit
                self.log.add("duo", "error", agent=n, text=f"could not deliver a message: {e}")

    def _send(self, n, text):
        self.outbox[n].put_nowait(text)

    def _broadcast(self, text):
        for n in self.agents:
            self._send(n, text)

    # --------------------------------------------------------------- events
    def _on_event(self, n, kind, data):
        self.log.add(n, kind, **data)
        if kind == "message":
            text = data.get("text", "")
            tags = READY.findall(text)
            self.ready[n] = tags[-1].lower() if tags else None
            if tags:
                self.log.add(n, "signal", ready=self.ready[n])
            self._send(OTHER[n], f"[{NAMES[n]}]: {text}")
            self._check_ready()
        elif kind in ("tool", "file_change"):
            self.nudges = 0
            detail = data.get("detail") or ", ".join(data.get("paths") or [])
            self.activity[n].append(detail if kind == "tool" else f"changed {detail}")

    def _turn_end(self, n):
        self.turns += 1
        if self.activity[n]:
            items = self.activity[n][:10]
            more = len(self.activity[n]) - len(items)
            line = "; ".join(items) + (f"; and {more} more" if more > 0 else "")
            self._send(OTHER[n], f"[{NAMES[n]} activity]: {line}")
            self.activity[n] = []
        self._schedule_idle_check()

    def _on_exit(self, n, code):
        self.log.add("duo", "error", agent=n, text=f"{NAMES[n]} stopped unexpectedly (exit {code}).")

    # ----------------------------------------------------------------- idle
    def _schedule_idle_check(self):
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = asyncio.ensure_future(self._idle_check())

    def _all_quiet(self):
        return (self.status == "running" and not any(a.busy for a in self.agents.values())
                and all(q.empty() for q in self.outbox.values()) and not self.cards)

    async def _idle_check(self):
        await asyncio.sleep(self.limits.idle_delay)
        if not self._all_quiet():
            return
        self.nudges += 1
        if self.nudges > self.limits.max_nudges:
            self._stalled()
            return
        self._broadcast("[duo] You are both idle. Keep going toward the goal, or say [[READY: done]] if it is "
                        "finished.")

    def _stalled(self):
        self.log.add("duo", "status", status="stalled", text="Both agents stayed idle after repeated nudges.")

    # ------------------------------------------------------------ approvals
    async def _approval(self, ap):
        decision, reason = classify(ap.request, self.ctx)
        if decision == "allow":
            if ap.request.tool == "write":
                p = ap.request.input.get("path", "")
                p = p if os.path.isabs(p) else os.path.join(self.ctx.workdir, p)
                if not os.path.exists(p):
                    self.ctx.mark_created(p)
            return "allow", ""
        if decision == "block":
            self.log.add("duo", "blocked", by=ap.agent, summary=ap.summary, reason=reason)
            return "deny", f"Blocked by duo: {reason}"
        answer, note = await self._card("action", by=ap.agent, summary=ap.summary, reason=reason)
        if answer == "approve":
            return "allow", ""
        return "deny", f"{self.user} denied this.{' ' + note if note else ''}"

    async def _card(self, card, **info):
        self._card_n += 1
        cid = f"c{self._card_n}"
        fut = self.loop.create_future()
        self.cards[cid] = {"future": fut, "card": card, **info}
        self.log.add("duo", "card_open", id=cid, card=card, **info)
        return await fut

    def resolve_card(self, card_id, decision, note=""):
        """Thread-safe: called from the web server."""
        self.loop.call_soon_threadsafe(self._resolve, card_id, decision, note)

    def _resolve(self, card_id, decision, note):
        c = self.cards.pop(card_id, None)
        if not c or c["future"].done():
            return
        decision = "approve" if decision == "approve" else "deny"
        self.log.add("user", "card_resolved", id=card_id, decision=decision, note=note)
        c["future"].set_result((decision, note))

    # ---------------------------------------------------------- plan / done
    def _check_ready(self):
        vals = set(self.ready.values())
        if len(vals) != 1 or None in vals:
            return
        which = vals.pop()
        if which == "plan" and not any(c["card"] == "plan" for c in self.cards.values()):
            path = os.path.join(self.run_dir, "plan.md")
            if not os.path.exists(path):
                self._reset_ready()
                self._broadcast(f"[duo] You both said the plan is ready, but {path} does not exist. Write it there, "
                                "then say [[READY: plan]] again.")
                return
            asyncio.ensure_future(self._plan_card(open(path).read()))
        elif which == "done" and self.phase == "build":
            path = os.path.join(self.run_dir, "summary.md")
            if not os.path.exists(path):
                self._reset_ready()
                self._broadcast(f"[duo] You both said it is done, but {path} does not exist. Write the summary "
                                "there, then say [[READY: done]] again.")
                return
            asyncio.ensure_future(self.finish("done"))

    def _reset_ready(self):
        self.ready = {n: None for n in self.agents}

    async def _plan_card(self, plan_text):
        answer, note = await self._card("plan", by="both", summary="The plan is ready for your approval.",
                                        reason="", plan=plan_text)
        self._reset_ready()
        if answer == "approve":
            self.phase = self.ctx.phase = "build"
            for a in self.agents.values():
                await a.set_phase("build")
            self.log.add("duo", "status", status="running", phase="build")
            self._broadcast(f"[duo] {self.user} approved the plan. Build it.{' Note: ' + note if note else ''}")
        else:
            self._broadcast(f"[{self.user} sent the plan back]: {note or 'Rework the plan.'}")

    async def finish(self, status):
        if self.status in ("done", "stopped"):
            return
        self.status = status
        for c in list(self.cards.values()):
            if not c["future"].done():
                c["future"].set_result(("deny", "run ended"))
        self.cards.clear()
        for a in self.agents.values():
            try:
                await a.close()
            except Exception:
                pass
        if self.report_fn:
            path = self.report_fn(self.run_dir, self.log.all(), self.workdir, status)
            self.log.add("duo", "report", path=path)
        self.log.add("duo", "status", status=status)
        if self._finished and not self._finished.done():
            self._finished.set_result(status)

    # ----------------------------------------------------------------- user
    def say(self, text):
        """Thread-safe: called from the web server."""
        self.loop.call_soon_threadsafe(self._say, text)

    def _say(self, text):
        m = MENTION.match(text)
        if m:
            to = sorted({w.lower() for w in re.findall(r"@(claude|codex)", m.group(1), re.I)})
            body = m.group(2).strip()
            self.log.add("user", "message", text=text, to=to)
            for n in to:
                self._send(n, f"[{self.user} to you]: {body}")
        else:
            self.log.add("user", "message", text=text, to=sorted(self.agents))
            self._broadcast(f"[{self.user} to both]: {text}")
        self.nudges = 0
