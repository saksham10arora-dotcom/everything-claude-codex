"""Claude Code driven headless over stream-json. Frame shapes: duo/PROTOCOL.md."""
import asyncio
import json
import os
import shlex
import tempfile

from duo.agents import Agent, Approval, short, summarize
from duo.policy import Request

FLAGS = ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
         "--permission-mode", "default", "--permission-prompts", "host", "--permission-prompt-tool", "stdio",
         "--no-session-persistence", "--settings", json.dumps({"disableAllHooks": True})]


def to_request(tool_name, tool_input):
    i = tool_input or {}
    if tool_name == "Bash":
        return Request("claude", "bash", {"command": i.get("command", "")})
    if tool_name == "Write":
        return Request("claude", "write", {"path": i.get("file_path", "")})
    if tool_name in ("Edit", "MultiEdit"):
        return Request("claude", "edit", {"path": i.get("file_path", "")})
    if tool_name == "NotebookEdit":
        return Request("claude", "edit", {"path": i.get("notebook_path", "")})
    if tool_name == "Read":
        return Request("claude", "read", {"path": i.get("file_path", "")})
    if tool_name in ("Glob", "Grep"):
        return Request("claude", "read", {"path": i.get("path", ".")})
    if tool_name == "WebFetch":
        return Request("claude", "web", {"url": i.get("url", "")})
    if tool_name == "WebSearch":
        return Request("claude", "web", {"url": i.get("query", "")})
    if tool_name.startswith("mcp__"):
        return Request("claude", "mcp", {"name": tool_name, "args": i})
    return Request("claude", tool_name, dict(i))


def parse_line(obj):
    """One stdout frame -> [(kind, data)]; kind "turn_end" marks the end of a turn."""
    t = obj.get("type")
    out = []
    if t == "assistant":
        for b in (obj.get("message") or {}).get("content") or []:
            bt = b.get("type")
            if bt == "text" and b.get("text", "").strip():
                out.append(("message", {"text": b["text"]}))
            elif bt == "tool_use":
                out.append(("tool", {"name": b.get("name"), "id": b.get("id"), "detail": short(b.get("input", {}))}))
            elif bt == "thinking" and b.get("thinking", "").strip():
                out.append(("reasoning", {"text": b["thinking"]}))
    elif t == "user":
        content = (obj.get("message") or {}).get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    text = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
                    out.append(("tool_result", {"id": b.get("tool_use_id"), "text": short(text, 400),
                                                "error": bool(b.get("is_error"))}))
    elif t == "result":
        out.append(("turn_end", {"status": obj.get("subtype"), "text": short(obj.get("result") or "", 400)}))
    return out


class ClaudeAgent(Agent):
    name = "claude"

    def __init__(self, workdir, model, effort):
        super().__init__()
        self.workdir, self.model, self.effort = workdir, model, effort
        self.proc = None
        self._reader = None
        self._closing = False
        self._n = 0

    def _cmd(self, brief_path):
        exe = shlex.split(os.environ.get("ECX_DUO_CLAUDE_BIN", "claude"))
        cmd = exe + FLAGS + ["--model", self.model, "--append-system-prompt-file", brief_path]
        if self.effort:
            cmd += ["--effort", self.effort]
        return cmd

    async def _write(self, obj):
        if self.proc and self.proc.stdin and not self.proc.stdin.is_closing():
            self.proc.stdin.write((json.dumps(obj) + "\n").encode())
            await self.proc.stdin.drain()

    def _rid(self):
        self._n += 1
        return f"duo-{self._n}"

    async def start(self, brief, first_message):
        fd, path = tempfile.mkstemp(prefix="duo-claude-brief-", suffix=".md")
        with os.fdopen(fd, "w") as f:
            f.write(brief)
        self._brief_path = path
        self.proc = await asyncio.create_subprocess_exec(
            *self._cmd(path), cwd=self.workdir, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=16 * 1024 * 1024)
        self._reader = asyncio.create_task(self._read())
        await self._write({"type": "control_request", "request_id": self._rid(), "request": {"subtype": "initialize"}})
        await self.send(first_message)

    async def _read(self):
        async for raw in self.proc.stdout:
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if obj.get("type") == "control_request" and (obj.get("request") or {}).get("subtype") == "can_use_tool":
                asyncio.create_task(self._permission(obj))
                continue
            for kind, data in parse_line(obj):
                if kind == "turn_end":
                    self.busy = False
                    self.on_turn_end()
                else:
                    self.on_event(kind, data)
        code = await self.proc.wait()
        if not self._closing:
            self.on_exit(code)

    async def _permission(self, obj):
        r = obj["request"]
        req = to_request(r.get("tool_name", ""), r.get("input") or {})
        try:
            decision, message = await self.on_approval(Approval("claude", req, summarize(req)))
        except Exception as e:  # never leave Claude hanging on a request
            decision, message = "deny", f"duo error: {e}"
        if decision == "allow":
            resp = {"behavior": "allow", "updatedInput": r.get("input") or {}}
        else:
            resp = {"behavior": "deny", "message": message or "Denied."}
        await self._write({"type": "control_response",
                           "response": {"subtype": "success", "request_id": obj["request_id"], "response": resp}})

    async def send(self, text):
        self.busy = True
        await self._write({"type": "user", "message": {"role": "user", "content": text}})

    async def interrupt(self):
        await self._write({"type": "control_request", "request_id": self._rid(), "request": {"subtype": "interrupt"}})

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
        if getattr(self, "_brief_path", None) and os.path.exists(self._brief_path):
            os.remove(self._brief_path)
