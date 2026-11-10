"""The shape every duo agent adapter has. The orchestrator only ever talks to this."""
import json
from dataclasses import dataclass

from duo.policy import Request, unwrap


@dataclass
class Approval:
    agent: str
    request: Request
    summary: str


def short(value, n=160):
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def summarize(req):
    """One line for an approval card."""
    i = req.input
    if req.tool == "bash":
        return short(unwrap(i.get("command", "")), 300)
    if req.tool in ("write", "edit", "delete", "read"):
        return f"{req.tool} {i.get('path', '')}"
    if req.tool == "mcp":
        return f"{i.get('name', '')} {short(i.get('args', {}), 200)}"
    if req.tool == "web":
        return short(i.get("url", ""), 200)
    return f"{req.tool} {short(i, 200)}"


class Agent:
    name = ""

    def __init__(self):
        self.busy = False
        self.on_event = lambda kind, data: None
        self.on_turn_end = lambda: None
        self.on_exit = lambda code: None

        async def _deny(approval):
            return "deny", "No approval handler."
        self.on_approval = _deny

    async def start(self, brief, first_message):
        raise NotImplementedError

    async def send(self, text):
        raise NotImplementedError

    async def interrupt(self):
        raise NotImplementedError

    async def close(self):
        raise NotImplementedError

    async def set_phase(self, phase):
        """Codex switches sandbox per phase; Claude needs nothing (the policy covers it)."""

    async def set_power(self, level):
        """"high": top model / effort from the next step on; "normal": back to the run's defaults."""
