import asyncio
import unittest

from duo.orchestrator import Limits
from duo.policy import Request
from tests.duo_fakes import make, tick


async def started(limits=None):
    o, a, log, work, rd = make(limits=limits or Limits(idle_delay=5))
    pings = []
    o.ping_fn = lambda title, text: pings.append(title)
    task = asyncio.ensure_future(o.run("goal"))
    await tick()
    return o, a, log, task, pings


def status(log):
    return [e for e in log.all() if e["kind"] == "status"]


class Control(unittest.TestCase):
    def test_pause_holds_forwarding(self):
        async def go():
            o, a, log, task, _ = await started()
            o.control("pause"); await tick()
            self.assertEqual(o.status, "paused")
            self.assertEqual((a["claude"].interrupted, a["codex"].interrupted), (1, 1))
            a["claude"].say("held message")
            await tick()
            self.assertNotIn("[Claude]: held message", a["codex"].sent)
            task.cancel()
        asyncio.run(go())

    def test_resume_flushes(self):
        async def go():
            o, a, log, task, _ = await started()
            o.control("pause"); await tick()
            a["claude"].say("held message"); await tick()
            o.control("resume"); await tick()
            self.assertEqual(o.status, "running")
            self.assertIn("[Claude]: held message", a["codex"].sent)
            self.assertTrue(any("resumed the run" in s for s in a["codex"].sent))
            task.cancel()
        asyncio.run(go())

    def test_stop_denies_open_cards_and_writes_report(self):
        async def go():
            o, a, log, task, _ = await started()
            fut = a["codex"].ask(Request("codex", "bash", {"command": "git push"}))
            await tick()
            o.control("stop"); await tick()
            self.assertEqual(fut.result()[0], "deny")
            self.assertEqual(task.result(), "stopped")
            self.assertEqual(o.reports, ["stopped"])
            self.assertTrue(a["claude"].closed and a["codex"].closed)
            self.assertGreaterEqual(a["codex"].interrupted, 1)
        asyncio.run(go())

    def test_turn_limit_pauses(self):
        async def go():
            o, a, log, task, pings = await started(Limits(max_turns=2, idle_delay=5))
            a["claude"].end_turn(); a["codex"].end_turn(); await tick()
            self.assertEqual(o.status, "paused")
            self.assertEqual(status(log)[-1].get("reason"), "turn limit reached (2)")
            self.assertEqual(len(pings), 1)
            task.cancel()
        asyncio.run(go())

    def test_time_limit_pauses(self):
        async def go():
            o, a, log, task, pings = await started(Limits(hours=0.05 / 3600, idle_delay=5))
            await asyncio.sleep(0.15)
            self.assertEqual(o.status, "paused")
            self.assertIn("time limit", status(log)[-1].get("reason"))
            task.cancel()
        asyncio.run(go())

    def test_agent_crash_ends_run_and_logs(self):
        async def go():
            o, a, log, task, pings = await started()
            a["codex"].on_exit(1); await tick()
            self.assertEqual(o.status, "crashed")
            self.assertTrue(any(e["kind"] == "error" and "Codex" in e["text"] for e in log.all()))
            self.assertEqual(len(pings), 1)
        asyncio.run(go())

    def test_circle_flag_once_per_streak(self):
        async def go():
            o, a, log, task, _ = await started(Limits(circle_after=3, idle_delay=5))
            for i in range(5):
                (a["claude"] if i % 2 else a["codex"]).say(f"no, you are wrong {i}")
            await tick()
            flags = [e for e in status(log) if e.get("flag") == "circles"]
            self.assertEqual(len(flags), 1)
            a["claude"].did("pytest"); 
            for i in range(3):
                a["codex"].say(f"still wrong {i}")
            await tick()
            self.assertEqual(len([e for e in status(log) if e.get("flag") == "circles"]), 2)
            task.cancel()
        asyncio.run(go())

    def test_stall_after_nudges_pauses(self):
        async def go():
            o, a, log, task, pings = await started(Limits(idle_delay=0.01, max_nudges=1))
            a["claude"].end_turn(); a["codex"].end_turn()
            await asyncio.sleep(0.05)
            a["claude"].end_turn()
            await asyncio.sleep(0.05)
            self.assertEqual(o.status, "paused")
            task.cancel()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
