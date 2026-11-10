"""Vault reads without cards, and the usage meter / limit pause."""
import asyncio
import os
import tempfile
import unittest

from duo.claude_agent import parse_line
from duo.codex_agent import parse_notification
from duo.orchestrator import Limits
from duo.policy import Ctx, Request, classify
from tests.duo_fakes import make, tick

WORK = os.path.realpath(tempfile.mkdtemp())
VAULT = os.path.realpath(tempfile.mkdtemp())


def bash(cmd):
    c = Ctx(workdir=WORK, phase="build", readable=[VAULT])
    return classify(Request("claude", "bash", {"command": cmd}), c)[0]


class VaultReads(unittest.TestCase):
    def test_read_only_commands_in_vault_allowed(self):
        self.assertEqual(bash(f"cd {VAULT}; sed -n 1,120p personal/a.md; echo ====; head -25 b.md"), "allow")
        self.assertEqual(bash(f'cd {VAULT}; grep -rli "edunomix" . --include=*.md 2>/dev/null | head -5'), "allow")

    def test_writes_in_vault_still_card(self):
        self.assertEqual(bash(f"cd {VAULT} && echo x > notes.md"), "card")
        self.assertEqual(bash(f"cd {VAULT} && rm a.md"), "card")
        self.assertEqual(bash(f"cd {VAULT} && python3 build.py"), "card")

    def test_other_folders_still_card(self):
        self.assertEqual(bash("cd /etc && cat hosts"), "card")


class Usage(unittest.TestCase):
    def test_claude_rate_limit_event(self):
        ev = parse_line({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": {
            "five_hour": {"utilization": 0.42, "resetsAt": 1}, "seven_day": {"utilization": 0.05, "resetsAt": 2}}}})
        self.assertEqual(ev, [("usage", {"five_hour": 42, "seven_day": 5, "resets": 1})])

    def test_codex_rate_limits_updated(self):
        ev = parse_notification("account/rateLimits/updated", {"rateLimits": {
            "primary": {"usedPercent": 31, "windowDurationMins": 300, "resetsAt": 7},
            "secondary": {"usedPercent": 7, "windowDurationMins": 10080, "resetsAt": 9}}})
        self.assertEqual(ev, [("usage", {"five_hour": 31, "seven_day": 7, "resets": 7})])

    def test_usage_logged_on_change_and_pauses_near_limit(self):
        async def go():
            o, a, log, work, rd = make(limits=Limits(idle_delay=5, usage_pause=90))
            pings = []
            o.ping_fn = lambda t, x: pings.append(x)
            task = asyncio.ensure_future(o.run("goal"))
            await tick()
            for pct in (40, 40, 41):
                a["claude"].on_event("usage", {"five_hour": pct, "seven_day": 5, "resets": 1})
            await tick()
            self.assertEqual([e["five_hour"] for e in log.all() if e["kind"] == "usage"], [40, 41])
            a["codex"].on_event("usage", {"five_hour": 92, "seven_day": 10, "resets": 1})
            await tick()
            self.assertEqual(o.status, "paused")
            self.assertTrue(any("Codex" in p and "92%" in p for p in pings))
            task.cancel()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
