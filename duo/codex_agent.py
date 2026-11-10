"""Codex driven over `codex app-server` (JSON-RPC on stdio). Frame shapes: duo/PROTOCOL.md."""
import ast
import asyncio
import json
import os
import re
import shlex

from duo.agents import Agent, Approval, short, summarize
from duo.policy import Request, unwrap

LINKED = ("auth.json", "config.toml", "AGENTS.md", "skills")  # never rules/, hooks.json, sessions/


def codex_home(real=None, home=None):
    """A duo-only Codex home: the user's login, config, AGENTS.md and skills, without their allow-rules or history."""
    real = real or os.path.expanduser("~/.codex")
    home = home or os.environ.get("ECX_DUO_CODEX_HOME") or os.path.expanduser("~/.ecx-duo/codex-home")
    os.makedirs(home, exist_ok=True)
    for name in LINKED:
        src, dst = os.path.join(real, name), os.path.join(home, name)
        if os.path.exists(src) and not os.path.lexists(dst):
            os.symlink(src, dst)
    return home


def mcp_servers(config_path):
    out = []
    try:
        lines = open(config_path).read().splitlines()
    except OSError:
        return out
    for ln in lines:
        m = re.match(r"^\s*\[mcp_servers\.([^.\]]+|\"[^\"]+\")\]\s*$", ln)
        if m:
            out.append(m.group(1).strip('"'))
    return out


def _paths(item):
    return [(c.get("path", ""), (c.get("kind") or {}).get("type", "update")) for c in item.get("changes") or []]


def parse_notification(method, params):
    """One notification -> [(kind, data)]. "turn_end" and "turn_started" are internal markers."""
    if method == "turn/started":
        return [("turn_started", {"id": (params.get("turn") or {}).get("id")})]
    if method == "turn/completed":
        return [("turn_end", {"status": (params.get("turn") or {}).get("status")})]
    if method == "account/rateLimits/updated":
        r = params.get("rateLimits") or {}
        p, s = r.get("primary") or {}, r.get("secondary") or {}
        return [("usage", {"five_hour": p.get("usedPercent"), "seven_day": s.get("usedPercent"), "resets": p.get("resetsAt")})]
    if method == "error":
        return [("error", {"text": short(params, 400)})]
    if method != "item/completed":
        return []
    it = params.get("item") or {}
    t = it.get("type")
    if t == "agentMessage" and (it.get("text") or "").strip():
        return [("message", {"text": it["text"]})]
    if t == "reasoning":
        parts = [p if isinstance(p, str) else p.get("text", "") for p in it.get("summary") or []]
        text = "\n".join(p for p in parts if p.strip())
        return [("reasoning", {"text": text})] if text else []
    if t == "commandExecution":
        cmd = unwrap(it.get("command") or "")
        out = [("tool", {"name": "shell", "detail": short(cmd, 300), "status": it.get("status")})]
        if it.get("aggregatedOutput") is not None or it.get("status") == "declined":
            out.append(("tool_result", {"text": short(it.get("aggregatedOutput") or it.get("status") or "", 400),
                                        "error": it.get("status") == "declined" or it.get("exitCode") not in (0, None)}))
        return out
    if t == "fileChange":
        ps = _paths(it)
        return [("file_change", {"paths": [p for p, _ in ps], "kinds": [k for _, k in ps], "status": it.get("status")})]
    if t == "mcpToolCall":
        return [("tool", {"name": f"mcp__{it.get('server')}__{it.get('tool')}", "detail": short(it.get("arguments") or ""),
                          "status": it.get("status")})]
    return []


def approval_to_request(method, params, items):
    if method in ("item/commandExecution/requestApproval", "execCommandApproval"):
        cmd = params.get("command")
        if isinstance(cmd, list):
            cmd = " ".join(shlex.quote(c) for c in cmd)
        return [Request("codex", "bash", {"command": cmd or ""})]
    if method in ("item/fileChange/requestApproval", "applyPatchApproval"):
        out = []
        for c in (items.get(params.get("itemId")) or {}).get("changes") or []:
            kind = c.get("kind") or {}
            t, path = kind.get("type"), c.get("path", "")
            if t == "update" and kind.get("move_path"):  # a rename: the old file goes away, a new one appears
                out += [Request("codex", "delete", {"path": path}), Request("codex", "write", {"path": kind["move_path"]})]
            elif t in ("add", "delete", "update"):
                out.append(Request("codex", {"add": "write", "delete": "delete", "update": "edit"}[t], {"path": path}))
            else:
                out.append(Request("codex", "unknown_patch", {"path": path, "kind": str(t)}))
        # duo cannot see which files this patch touches: ask instead of guessing
        return out or [Request("codex", "unknown_patch", {"path": "(files unknown to duo)"})]
    if method == "mcpServer/elicitation/request" and (params.get("_meta") or {}).get("codex_approval_kind") == "mcp_tool_call":
        m = re.search(r'run tool "([^"]+)"', params.get("message") or "")
        raw = (params.get("_meta") or {}).get("tool_params") or "{}"
        try:
            args = ast.literal_eval(raw) if isinstance(raw, str) else raw
        except (ValueError, SyntaxError):
            args = {"raw": raw}
        return [Request("codex", "mcp", {"name": f"mcp__{params.get('serverName')}__{m.group(1) if m else 'unknown'}",
                                         "args": args})]
    return []


class CodexAgent(Agent):
    name = "codex"

    def __init__(self, workdir, model, effort):
        super().__init__()
        self.workdir, self.model, self.effort = workdir, model, effort
        self.proc = None
        self.thread = None
        self.turn = None
        self.phase = "plan"
        self._id = 0
        self._waiting = {}
        self._items = {}
        self._queue = []
        self._closing = False
        self._reader = None

    def _cmd(self, home):
        exe = shlex.split(os.environ.get("ECX_DUO_CODEX_BIN", "codex"))
        # plugins off: their MCP servers cannot take a per-server approval setting, so their calls could skip cards
        cmd = exe + ["app-server", "-c", "features.codex_hooks=false", "-c", "features.plugins=false",
                     "-c", 'apps._default.default_tools_approval_mode="prompt"']
        for s in self._known_mcp(home):
            cmd += ["-c", f'mcp_servers.{s}.default_tools_approval_mode="prompt"']
        return cmd

    async def _write(self, obj):
        if self.proc and not self.proc.stdin.is_closing():
            self.proc.stdin.write((json.dumps({"jsonrpc": "2.0", **obj}) + "\n").encode())
            await self.proc.stdin.drain()

    async def _call(self, method, params):
        self._id += 1
        fut = asyncio.get_running_loop().create_future()
        self._waiting[self._id] = fut
        await self._write({"id": self._id, "method": method, "params": params})
        msg = await asyncio.wait_for(fut, 120)
        if "error" in msg:
            raise RuntimeError(f"codex {method}: {msg['error']}")
        return msg.get("result") or {}

    async def _launch(self, home):
        self.proc = await asyncio.create_subprocess_exec(
            *self._cmd(home), cwd=self.workdir, env={**os.environ, "CODEX_HOME": home},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=self._stderr(),
            limit=16 * 1024 * 1024)
        self._reader = asyncio.create_task(self._read())
        await self._call("initialize", {"clientInfo": {"name": "ecx-duo", "version": "1"}})
        await self._write({"method": "initialized"})

    BUILTIN_MCP = {"codex_apps"}  # ChatGPT app connectors; gated by apps._default above

    def _known_mcp(self, home):
        """MCP servers from the user's and the project's Codex config: each gets approval prompts forced on."""
        return sorted(set(mcp_servers(os.path.join(home, "config.toml")))
                      | set(mcp_servers(os.path.join(self.workdir, ".codex", "config.toml"))))

    async def _loaded_mcp(self):
        try:
            res = await self._call("mcpServerStatus/list", {"detail": "toolsAndAuthOnly"})
        except (RuntimeError, asyncio.TimeoutError):
            return []
        return [d.get("name") for d in res.get("data") or [] if d.get("name")]

    async def start(self, brief, first_message):
        home = codex_home()
        await self._launch(home)
        known = set(self._known_mcp(home)) | self.BUILTIN_MCP
        unknown = [n for n in await self._loaded_mcp() if n not in known]
        if unknown:  # never run a tool server whose calls would skip the approval cards
            raise RuntimeError(f"Codex loaded MCP servers duo cannot gate: {', '.join(unknown)}. Define them as "
                               "[mcp_servers.<name>] in ~/.codex/config.toml or the project's .codex/config.toml.")
        params = {"cwd": self.workdir, "ephemeral": True, "approvalPolicy": "untrusted", "sandbox": "read-only",
                  "developerInstructions": brief}
        if self.model:
            params["model"] = self.model
        self.thread = (await self._call("thread/start", params))["thread"]["id"]
        self.busy = False  # no turn exists yet, whatever anyone set before start
        await self.send(first_message)

    def _stderr(self):
        path = getattr(self, "stderr_path", None)
        return open(path, "ab") if path else asyncio.subprocess.DEVNULL

    def _sandbox(self):
        return {"type": "readOnly"} if self.phase == "plan" else {"type": "workspaceWrite", "networkAccess": True}

    async def set_phase(self, phase):
        self.phase = phase

    async def set_power(self, level):
        if not hasattr(self, "_base_effort"):
            self._base_effort = self.effort
        self.effort = "high" if level == "high" else self._base_effort  # applies from Codex's next turn

    async def send(self, text):
        inp = [{"type": "text", "text": text}]
        if self.busy and self.turn:
            try:
                await self._call("turn/steer", {"threadId": self.thread, "expectedTurnId": self.turn, "input": inp})
                return
            except RuntimeError:
                pass  # turn ended in between; start a new one
        if self.busy:
            self._queue.append(text)  # turn is starting; deliver after it ends
            return
        self.busy = True
        params = {"threadId": self.thread, "input": inp, "sandboxPolicy": self._sandbox()}
        if self.effort:
            params["effort"] = self.effort
        try:
            res = await self._call("turn/start", params)
        except Exception:
            self.busy = False  # no turn is running; never leave later messages stuck in the queue
            raise
        self.turn = (res.get("turn") or {}).get("id") or self.turn

    async def _read(self):
        async for raw in self.proc.stdout:
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if "id" in msg and "method" not in msg:
                fut = self._waiting.pop(msg["id"], None)
                if fut and not fut.done():
                    fut.set_result(msg)
                continue
            if "id" in msg:
                asyncio.create_task(self._server_request(msg))
                continue
            method, params = msg.get("method"), msg.get("params") or {}
            if method == "item/started":
                it = params.get("item") or {}
                if it.get("id"):
                    self._items[it["id"]] = it
            for kind, data in parse_notification(method, params):
                if kind == "turn_started":
                    self.turn = data["id"]
                elif kind == "turn_end":
                    self.busy, self.turn = False, None
                    self.on_turn_end()
                    if self._queue:
                        text = "\n\n".join(self._queue)
                        self._queue.clear()
                        asyncio.create_task(self.send(text))
                else:
                    self.on_event(kind, data)
        code = await self.proc.wait()
        for fut in self._waiting.values():
            if not fut.done():
                fut.set_result({"error": "app-server exited"})
        if not self._closing:
            self.on_exit(code)

    async def _server_request(self, msg):
        method, params = msg["method"], msg.get("params") or {}
        reqs = approval_to_request(method, params, self._items)
        is_mcp = method == "mcpServer/elicitation/request"
        if not reqs:
            self.on_event("blocked", {"reason": f"duo cannot answer {method}; declined.", "detail": short(params, 300)})
            result = {"action": "decline"} if is_mcp else {"decision": "decline"}
            if method in ("item/tool/requestUserInput", "item/permissions/requestApproval", "item/tool/call",
                          "account/chatgptAuthTokens/refresh", "attestation/generate"):
                await self._write({"id": msg["id"], "error": {"code": -32601, "message": "not supported by duo"}})
                return
            await self._write({"id": msg["id"], "result": result})
            return
        decision = "allow"
        for req in reqs:  # one denied path declines the whole batch
            try:
                d, _ = await self.on_approval(Approval("codex", req, summarize(req)))
            except Exception:
                d = "deny"
            if d != "allow":
                decision = "deny"
                break
        if is_mcp:
            result = {"action": "accept", "content": {}} if decision == "allow" else {"action": "decline"}
        else:
            result = {"decision": "accept" if decision == "allow" else "decline"}
        await self._write({"id": msg["id"], "result": result})

    async def interrupt(self):
        if self.thread and self.turn:
            try:
                await self._call("turn/interrupt", {"threadId": self.thread, "turnId": self.turn})
            except (RuntimeError, asyncio.TimeoutError):
                pass

    async def close(self):
        self._closing = True
        if not self.proc:
            return
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            await asyncio.wait_for(self.proc.wait(), 10)
        except asyncio.TimeoutError:
            self.proc.kill()
        if self._reader:
            await asyncio.gather(self._reader, return_exceptions=True)
