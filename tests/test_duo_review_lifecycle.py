"""Lifecycle findings from the whole-branch review (I2-I5)."""
import asyncio
import unittest

from duo.orchestrator import Limits
from duo.policy import Request
from tests.duo_fakes import FakeAgent, make, tick


class Exploding(FakeAgent):
    async def start(self, brief, first_message):
        raise RuntimeError("codex binary missing")


class SlowInterrupt(FakeAgent):
    async def interrupt(self):
        await asyncio.sleep(60)


async def started(**kw):
    o, a, log, work, rd = make(limits=Limits(idle_delay=5), **kw)
    o.ping_fn = lambda t, x: None
    task = asyncio.ensure_future(o.run("goal"))
    await tick()
    return o, a, log, task


class Lifecycle(unittest.TestCase):
    def test_crash_finishes_with_report(self):
        async def go():
            o, a, log, task = await started()
            a["codex"].on_exit(1)
            await tick()
            self.assertEqual(task.result(), "crashed")
            self.assertEqual(o.reports, ["crashed"])
            self.assertTrue(a["claude"].closed)
        asyncio.run(go())

    def test_failed_start_closes_other_and_reports(self):
        async def go():
            o, a, log, work, rd = make(limits=Limits(idle_delay=5))
            o.agents["codex"] = bad = Exploding("codex")
            o._wire("codex", bad)
            status = await asyncio.wait_for(o.run("goal"), 5)
            self.assertEqual(status, "failed")
            self.assertTrue(a["claude"].closed)
            self.assertEqual(o.reports, ["failed"])
            self.assertTrue(any(e["kind"] == "error" and "codex binary missing" in e["text"] for e in log.all()))
        asyncio.run(go())

    def test_report_error_still_finishes(self):
        async def go():
            o, a, log, task = await started()

            def boom(*args):
                raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")
            o.report_fn = boom
            o.control("stop")
            self.assertEqual(await asyncio.wait_for(task, 5), "stopped")
            self.assertTrue(any(e["kind"] == "error" and "report" in e["text"] for e in log.all()))
        asyncio.run(go())

    def test_stop_denies_and_logs_cards_before_slow_interrupts(self):
        async def go():
            o, a, log, work, rd = make(limits=Limits(idle_delay=5))
            slow = SlowInterrupt("codex")
            o.agents["codex"] = slow
            o._wire("codex", slow)
            o.interrupt_timeout = 0.05
            task = asyncio.ensure_future(o.run("goal"))
            await tick()
            fut = slow.ask(Request("codex", "bash", {"command": "git push"}))
            await tick()
            o.control("stop")
            self.assertEqual(await asyncio.wait_for(task, 3), "stopped")
            self.assertEqual(fut.result()[0], "deny")
            resolved = [e for e in log.all() if e["kind"] == "card_resolved"]
            self.assertEqual([(e["decision"], e["note"]) for e in resolved], [("deny", "run stopped")])
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
