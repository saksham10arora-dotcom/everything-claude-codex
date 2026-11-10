"""The High switch (top models mid-run) and per-agent working/idle events for the page."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
import urllib.request
from unittest import mock

from duo.claude_agent import ClaudeAgent
from duo.events import EventLog
from duo.orchestrator import Limits
from duo.server import start_server
from tests.duo_fakes import make, tick

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "duo")


class Power(unittest.TestCase):
    def test_high_and_normal_switch_both_agents(self):
        async def go():
            o, a, log, work, rd = make(limits=Limits(idle_delay=5))
            task = asyncio.ensure_future(o.run("goal"))
            await tick()
            o.control("high"); await tick()
            self.assertEqual((a["claude"].power, a["codex"].power), ("high", "high"))
            self.assertEqual([e.get("power") for e in log.all() if e.get("power")][-1], "high")
            o.control("normal"); await tick()
            self.assertEqual(a["codex"].power, "normal")
            task.cancel()
        asyncio.run(go())

    def test_claude_high_sends_set_model(self):
        out = tempfile.mktemp()
        env = {"ECX_DUO_CLAUDE_BIN": f"{sys.executable} {os.path.join(FIX, 'fake_claude.py')}", "FAKE_OUT": out}

        async def go():
            a = ClaudeAgent(tempfile.mkdtemp(), "sonnet", "medium")
            await a.start("B", "go")
            await a.set_power("high")
            await a.set_power("normal")
            await asyncio.sleep(0.2)
            await a.close()
        with mock.patch.dict(os.environ, env):
            asyncio.run(go())
        sent = [json.loads(l) for l in open(out)]
        models = [f["request"]["model"] for f in sent if f.get("request", {}).get("subtype") == "set_model"]
        self.assertEqual(models, ["opus", "sonnet"])

    def test_server_accepts_high(self):
        rd = tempfile.mkdtemp()
        calls = []

        class O:
            def control(self, a): calls.append(a)
        url, stop = start_server(EventLog(os.path.join(rd, "e.jsonl")), O(), rd)
        tok = url.split("t=")[1]
        req = urllib.request.Request(url.split("/?")[0] + "/control", data=json.dumps({"action": "high"}).encode(),
                                     method="POST", headers={"X-Duo-Token": tok})
        urllib.request.urlopen(req, timeout=5)
        stop()
        self.assertEqual(calls, ["high"])


class Turns(unittest.TestCase):
    def test_working_and_idle_events(self):
        async def go():
            o, a, log, work, rd = make(limits=Limits(idle_delay=5))
            task = asyncio.ensure_future(o.run("goal"))
            await tick()
            a["claude"].say("hello")
            await tick()
            a["codex"].end_turn()
            await tick()
            turns = [(e["who"], e["state"]) for e in log.all() if e["kind"] == "turn"]
            self.assertIn(("codex", "working"), turns)
            self.assertEqual(turns[-1], ("codex", "idle"))
            task.cancel()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
