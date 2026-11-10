"""Council opening: blind drafts, then each critiques the other's plan, then they merge."""
import asyncio
import os
import unittest

from duo.orchestrator import Limits
from tests.duo_fakes import make, tick


async def started():
    o, a, log, work, rd = make(limits=Limits(idle_delay=5), council=True)
    task = asyncio.ensure_future(o.run("goal"))
    await tick()
    return o, a, log, rd, task


def kinds(log, k):
    return [e for e in log.all() if e["kind"] == k]


class Council(unittest.TestCase):
    def test_starts_blind_with_draft_instructions(self):
        async def go():
            o, a, log, rd, task = await started()
            self.assertEqual(o.phase, "council")
            self.assertIn(os.path.join(rd, "draft-claude.md"), a["claude"].started[1])
            self.assertIn("[[READY: draft]]", a["codex"].started[1])
            task.cancel()
        asyncio.run(go())

    def test_messages_not_forwarded_while_blind(self):
        async def go():
            o, a, log, rd, task = await started()
            a["claude"].say("my plan is X")
            await tick()
            self.assertFalse(any("my plan is X" in s for s in a["codex"].sent))
            self.assertEqual(kinds(log, "message")[-1]["text"], "my plan is X")  # the user still sees it
            task.cancel()
        asyncio.run(go())

    def test_both_drafts_trigger_cross_critique(self):
        async def go():
            o, a, log, rd, task = await started()
            open(os.path.join(rd, "draft-claude.md"), "w").write("CLAUDE-PLAN")
            open(os.path.join(rd, "draft-codex.md"), "w").write("CODEX-PLAN")
            a["claude"].say("done [[READY: draft]]")
            await tick()
            self.assertEqual(o.phase, "council")
            a["codex"].say("[[READY: draft]]")
            await tick()
            self.assertEqual(o.phase, "plan")
            self.assertTrue(any("CODEX-PLAN" in s and "critique" in s.lower() for s in a["claude"].sent))
            self.assertTrue(any("CLAUDE-PLAN" in s for s in a["codex"].sent))
            self.assertFalse(any("CLAUDE-PLAN" in s for s in a["claude"].sent))
            d = kinds(log, "drafts")[0]
            self.assertEqual((d["claude"], d["codex"]), ("CLAUDE-PLAN", "CODEX-PLAN"))
            a["claude"].say("their step 2 is better")
            await tick()
            self.assertIn("[Claude]: their step 2 is better", a["codex"].sent)  # talking again after the blind round
            task.cancel()
        asyncio.run(go())

    def test_ready_without_draft_file_asks_for_it(self):
        async def go():
            o, a, log, rd, task = await started()
            a["claude"].say("[[READY: draft]]")
            a["codex"].say("[[READY: draft]]")
            await tick()
            self.assertEqual(o.phase, "council")
            self.assertTrue(any("draft-claude.md" in s and "does not exist" in s for s in a["claude"].sent))
            task.cancel()
        asyncio.run(go())

    def test_no_council_starts_in_plan(self):
        async def go():
            o, a, log, work, rd = make(limits=Limits(idle_delay=5))
            task = asyncio.ensure_future(o.run("goal"))
            await tick()
            self.assertEqual(o.phase, "plan")
            task.cancel()
        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
