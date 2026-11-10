"""Evidence rule (objections must be settled by evidence) and cross-verification (done = verified by the other)."""
import asyncio
import os
import unittest

from duo.orchestrator import Limits
from duo import report
from tests.duo_fakes import make, tick


async def building():
    o, a, log, work, rd = make(limits=Limits(idle_delay=5))
    task = asyncio.ensure_future(o.run("goal"))
    await tick()
    o.phase = o.ctx.phase = "build"
    open(os.path.join(rd, "summary.md"), "w").write("built")
    return o, a, log, rd, task


def flags(log):
    return [e.get("flag") for e in log.all() if e["kind"] == "status" and e.get("flag")]


class Evidence(unittest.TestCase):
    def test_open_objection_blocks_done(self):
        async def go():
            o, a, log, rd, task = await building()
            a["codex"].say("[[OBJECTION: the cache can serve stale prices]]")
            a["claude"].say("[[READY: done]]"); a["codex"].say("[[READY: done]]")
            await tick()
            self.assertFalse(task.done())
            self.assertTrue(any("open objection" in s and "stale prices" in s for s in a["codex"].sent))
            task.cancel()
        asyncio.run(go())

    def test_conceding_without_evidence_is_flagged(self):
        async def go():
            o, a, log, rd, task = await building()
            a["codex"].say("[[OBJECTION: the cache can serve stale prices]]")
            a["claude"].say("I think it's fine.")
            a["codex"].say("Fair point, you're right.")
            await tick()
            self.assertIn("conceded-without-evidence", flags(log))
            self.assertTrue(any("no new evidence" in s for s in a["codex"].sent))
            task.cancel()
        asyncio.run(go())

    def test_conceding_after_evidence_is_fine(self):
        async def go():
            o, a, log, rd, task = await building()
            a["codex"].say("[[OBJECTION: the cache can serve stale prices]]")
            a["claude"].did("python3 -m pytest tests/test_cache.py -q")
            a["codex"].say("You're right, that test proves it. [[RESOLVED: stale prices | test_cache passes]]")
            await tick()
            self.assertNotIn("conceded-without-evidence", flags(log))
            self.assertEqual(o.open_objections, {})
            task.cancel()
        asyncio.run(go())

    def test_stuck_disagreement_goes_to_the_user(self):
        async def go():
            o, a, log, rd, task = await building()
            a["codex"].say("[[OBJECTION: use postgres not sqlite]]")
            for i in range(6):
                (a["claude"] if i % 2 == 0 else a["codex"]).say(f"no, my way {i}")
            await tick()
            self.assertIn("disagreement", flags(log))
            self.assertTrue(any("strongest evidence" in s for s in a["claude"].sent))
            task.cancel()
        asyncio.run(go())


class Verification(unittest.TestCase):
    def test_done_needs_verification_of_the_others_changes(self):
        async def go():
            o, a, log, rd, task = await building()
            a["claude"].on_event("tool", {"name": "Edit", "detail": '{"file_path": "app.py"}'})
            a["claude"].say("[[READY: done]]"); a["codex"].say("[[READY: done]]")
            await tick()
            self.assertFalse(task.done())
            self.assertTrue(any("verify" in s.lower() and "Claude" in s for s in a["codex"].sent))
            a["codex"].say("[[VERIFIED: app.py change | ran pytest, 12 passed]] [[READY: done]]")
            a["claude"].say("[[READY: done]]")
            await tick()
            self.assertEqual(task.result(), "done")
        asyncio.run(go())

    def test_verification_must_come_after_the_latest_change(self):
        async def go():
            o, a, log, rd, task = await building()
            a["codex"].say("[[VERIFIED: early look | read it]]")
            a["claude"].on_event("file_change", {"paths": ["/w/app.py"], "kinds": ["update"], "status": "completed"})
            a["claude"].say("[[READY: done]]"); a["codex"].say("[[READY: done]]")
            await tick()
            self.assertFalse(task.done())
            task.cancel()
        asyncio.run(go())

    def test_no_changes_no_verification_needed(self):
        async def go():
            o, a, log, rd, task = await building()
            a["claude"].say("[[READY: done]]"); a["codex"].say("[[READY: done]]")
            await tick()
            self.assertEqual(task.result(), "done")
        asyncio.run(go())

    def test_report_lists_verifications_and_objections(self):
        events = [{"seq": 1, "ts": 1, "agent": "codex", "kind": "signal", "verified": "app.py | pytest 12 passed"},
                  {"seq": 2, "ts": 2, "agent": "claude", "kind": "signal", "objection": "stale cache"},
                  {"seq": 3, "ts": 3, "agent": "claude", "kind": "signal", "resolved": "stale cache | test added"}]
        a = report.audit(events, "/w")
        self.assertIn("app.py | pytest 12 passed", a)
        self.assertIn("stale cache", a)


if __name__ == "__main__":
    unittest.main()


class Bench(unittest.TestCase):
    def test_autoapprove_env_approves_cards_but_not_blocks(self):
        from unittest import mock
        from duo.policy import Request

        async def go():
            o, a, log, rd, task = await building()
            ok = await a["codex"].ask(Request("codex", "bash", {"command": "git push"}))
            bad = await a["codex"].ask(Request("codex", "bash", {"command": "rm -rf ~"}))
            self.assertEqual((ok[0], bad[0]), ("allow", "deny"))
            self.assertEqual([e["agent"] for e in log.all() if e["kind"] == "card_resolved"], ["duo"])
            task.cancel()
        with mock.patch.dict(os.environ, {"ECX_DUO_AUTOAPPROVE": "1"}):
            asyncio.run(go())

    def test_catchup_can_be_switched_off(self):
        from unittest import mock
        from duo import context
        with mock.patch.dict(os.environ, {"ECX_DUO_CATCHUP": "0", "ECX_DUO_CONTEXT": ""}):
            self.assertNotIn("recent normal Claude", context.brief("Claude", "Codex", "g", "u", "/r"))
