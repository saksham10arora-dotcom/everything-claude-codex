"""A scriptable stand-in agent for orchestrator tests."""
import asyncio
import os
import tempfile

from duo.agents import Agent, Approval, summarize
from duo.events import EventLog
from duo.orchestrator import Limits, Orchestrator
from duo.policy import Ctx


class FakeAgent(Agent):
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.sent, self.closed, self.interrupted, self.phase, self.started = [], False, 0, None, None

    async def start(self, brief, first_message):
        self.started = (brief, first_message)
        self.sent.append(first_message)

    async def send(self, text):
        self.sent.append(text)

    async def interrupt(self):
        self.interrupted += 1

    async def close(self):
        self.closed = True

    async def set_phase(self, phase):
        self.phase = phase

    async def set_power(self, level):
        self.power = level

    # test helpers
    def say(self, text):
        self.on_event("message", {"text": text})

    def did(self, detail):
        self.on_event("tool", {"name": "Bash", "detail": detail})

    def end_turn(self):
        self.busy = False
        self.on_turn_end()

    def ask(self, req):
        return asyncio.ensure_future(self.on_approval(Approval(self.name, req, summarize(req))))


async def tick(n=3):
    for _ in range(n):
        await asyncio.sleep(0.01)


def make(limits=None, existed=()):
    work = os.path.realpath(tempfile.mkdtemp())
    run_dir = os.path.join(work, ".duo", "r1")
    os.makedirs(run_dir)
    log = EventLog(os.path.join(run_dir, "events.jsonl"))
    agents = {"claude": FakeAgent("claude"), "codex": FakeAgent("codex")}
    ctx = Ctx(workdir=work, phase="plan", existed={os.path.join(work, p) for p in existed})
    reports = []

    def report(run_dir_, events, workdir, status):
        reports.append(status)
        return os.path.join(run_dir_, "report.md")

    o = Orchestrator(work, run_dir, agents, log, ctx, "Saksham", limits or Limits(idle_delay=0.02),
                     brief_fn=lambda me, other, goal, user, rd: f"BRIEF {me}", report_fn=report)
    o.reports = reports
    return o, agents, log, work, run_dir
