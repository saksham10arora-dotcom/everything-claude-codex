import asyncio
import os
import unittest

from duo.policy import Request
from tests.duo_fakes import make, tick


def run(coro):
    return asyncio.run(coro)


async def started(**kw):
    o, a, log, work, rd = make(**kw)
    task = asyncio.ensure_future(o.run("fix the bug"))
    await tick()
    return o, a, log, work, rd, task


def kinds(log, kind):
    return [e for e in log.all() if e["kind"] == kind]


class Orchestrate(unittest.TestCase):
    def test_both_started_with_brief_and_goal(self):
        async def go():
            o, a, log, *_ , task = await started()
            self.assertEqual(a["claude"].started[0], "BRIEF Claude")
            self.assertIn("fix the bug", a["codex"].started[1])
            task.cancel()
        run(go())

    def test_message_forwarded_with_prefix(self):
        async def go():
            o, a, log, *_, task = await started()
            a["claude"].say("I think we should use sqlite")
            await tick()
            self.assertIn("[Claude]: I think we should use sqlite", a["codex"].sent)
            self.assertNotIn("[Claude]: I think we should use sqlite", a["claude"].sent)
            self.assertEqual(kinds(log, "message")[0]["agent"], "claude")
            task.cancel()
        run(go())

    def test_mention_routes_to_one(self):
        async def go():
            o, a, log, *_, task = await started()
            o.say("@codex agree with Claude on this")
            await tick()
            self.assertIn("[Saksham to you]: agree with Claude on this", a["codex"].sent)
            self.assertFalse(any(s.startswith("[Saksham to you]") for s in a["claude"].sent))
            self.assertEqual(kinds(log, "message")[-1]["to"], ["codex"])
            task.cancel()
        run(go())

    def test_both_mentions_and_no_mention(self):
        async def go():
            o, a, log, *_, task = await started()
            o.say("ship the smaller version")
            o.say("@Claude @codex stop arguing")
            await tick()
            for n in ("claude", "codex"):
                self.assertIn("[Saksham to both]: ship the smaller version", a[n].sent)
                self.assertIn("[Saksham to you]: stop arguing", a[n].sent)
            task.cancel()
        run(go())

    def test_card_waits_for_user(self):
        async def go():
            o, a, log, *_, task = await started()
            fut = a["codex"].ask(Request("codex", "bash", {"command": "git push"}))
            await tick()
            self.assertFalse(fut.done())
            card = kinds(log, "card_open")[0]
            self.assertEqual((card["card"], card["by"]), ("action", "codex"))
            o.resolve_card(card["id"], "approve")
            await tick()
            self.assertEqual(fut.result()[0], "allow")
            self.assertEqual(kinds(log, "card_resolved")[0]["decision"], "approve")
            task.cancel()
        run(go())

    def test_denied_card_returns_note(self):
        async def go():
            o, a, log, *_, task = await started()
            fut = a["claude"].ask(Request("claude", "bash", {"command": "git push"}))
            await tick()
            o.resolve_card(kinds(log, "card_open")[0]["id"], "deny", "not yet")
            await tick()
            self.assertEqual(fut.result()[0], "deny")
            self.assertIn("not yet", fut.result()[1])
            task.cancel()
        run(go())

    def test_block_never_reaches_user(self):
        async def go():
            o, a, log, *_, task = await started()
            fut = a["claude"].ask(Request("claude", "bash", {"command": "rm -rf ~"}))
            await tick()
            self.assertEqual(fut.result()[0], "deny")
            self.assertEqual(kinds(log, "card_open"), [])
            self.assertEqual(len(kinds(log, "blocked")), 1)
            task.cancel()
        run(go())

    def test_allowed_new_write_marks_created(self):
        async def go():
            o, a, log, work, rd, task = await started()
            o.ctx.phase = "build"
            fut = a["claude"].ask(Request("claude", "write", {"path": os.path.join(work, "new.py")}))
            await tick()
            self.assertEqual(fut.result()[0], "allow")
            self.assertIn(os.path.join(work, "new.py"), o.ctx.created)
            task.cancel()
        run(go())

    def test_plan_card_when_both_ready(self):
        async def go():
            o, a, log, work, rd, task = await started()
            open(os.path.join(rd, "plan.md"), "w").write("- [ ] step one")
            a["claude"].say("plan looks right [[READY: plan]]")
            await tick()
            self.assertEqual(kinds(log, "card_open"), [])
            a["codex"].say("agreed [[READY: plan]]")
            await tick()
            card = kinds(log, "card_open")[0]
            self.assertEqual(card["card"], "plan")
            self.assertIn("step one", card["plan"])
            task.cancel()
        run(go())

    def test_missing_plan_file_asks_them_to_write_it(self):
        async def go():
            o, a, log, work, rd, task = await started()
            a["claude"].say("[[READY: plan]]")
            a["codex"].say("[[READY: plan]]")
            await tick()
            self.assertEqual(kinds(log, "card_open"), [])
            self.assertTrue(any("does not exist" in s for s in a["claude"].sent))
            task.cancel()
        run(go())

    def test_readiness_clears_on_untagged_message(self):
        async def go():
            o, a, log, work, rd, task = await started()
            open(os.path.join(rd, "plan.md"), "w").write("- [ ] x")
            a["claude"].say("[[READY: plan]]")
            a["claude"].say("actually wait, one more thing")
            a["codex"].say("[[READY: plan]]")
            await tick()
            self.assertEqual(kinds(log, "card_open"), [])
            task.cancel()
        run(go())

    def test_plan_approve_switches_phase(self):
        async def go():
            o, a, log, work, rd, task = await started()
            open(os.path.join(rd, "plan.md"), "w").write("- [ ] x")
            a["claude"].say("[[READY: plan]]"); a["codex"].say("[[READY: plan]]")
            await tick()
            o.resolve_card(kinds(log, "card_open")[0]["id"], "approve")
            await tick()
            self.assertEqual((o.phase, o.ctx.phase), ("build", "build"))
            self.assertEqual((a["claude"].phase, a["codex"].phase), ("build", "build"))
            self.assertTrue(any("approved the plan" in s for s in a["codex"].sent))
            task.cancel()
        run(go())

    def test_plan_deny_forwards_note(self):
        async def go():
            o, a, log, work, rd, task = await started()
            open(os.path.join(rd, "plan.md"), "w").write("- [ ] x")
            a["claude"].say("[[READY: plan]]"); a["codex"].say("[[READY: plan]]")
            await tick()
            o.resolve_card(kinds(log, "card_open")[0]["id"], "deny", "too big, cut step 3")
            await tick()
            self.assertEqual(o.phase, "plan")
            self.assertIn("[Saksham sent the plan back]: too big, cut step 3", a["claude"].sent)
            self.assertEqual(o.ready, {"claude": None, "codex": None})
            task.cancel()
        run(go())

    def test_done_requires_summary(self):
        async def go():
            o, a, log, work, rd, task = await started()
            o.phase = o.ctx.phase = "build"
            a["claude"].say("[[READY: done]]"); a["codex"].say("[[READY: done]]")
            await tick()
            self.assertFalse(task.done())
            self.assertTrue(any("summary.md" in s for s in a["claude"].sent))
            open(os.path.join(rd, "summary.md"), "w").write("built it")
            a["claude"].say("written [[READY: done]]"); a["codex"].say("[[READY: done]]")
            await tick()
            self.assertEqual(task.result(), "done")
            self.assertEqual(o.reports, ["done"])
            self.assertTrue(a["claude"].closed and a["codex"].closed)
        run(go())

    def test_activity_line_at_turn_end(self):
        async def go():
            o, a, log, *_, task = await started()
            a["codex"].did("pytest -q")
            a["codex"].did("edit app.py")
            a["codex"].end_turn()
            await tick()
            self.assertIn("[Codex activity]: pytest -q; edit app.py", a["claude"].sent)
            task.cancel()
        run(go())

    def test_idle_nudge(self):
        async def go():
            o, a, log, *_, task = await started()
            a["claude"].end_turn(); a["codex"].end_turn()
            await asyncio.sleep(0.1)
            for n in ("claude", "codex"):
                self.assertTrue(any("You are both idle" in s for s in a[n].sent))
            task.cancel()
        run(go())

    def test_no_nudge_while_card_open(self):
        async def go():
            o, a, log, *_, task = await started()
            a["codex"].ask(Request("codex", "bash", {"command": "git push"}))
            await tick()
            a["claude"].end_turn(); a["codex"].end_turn()
            await asyncio.sleep(0.1)
            self.assertFalse(any("You are both idle" in s for s in a["claude"].sent))
            task.cancel()
        run(go())


if __name__ == "__main__":
    unittest.main()


class SmokeFixes(unittest.TestCase):
    def test_quiet_is_not_forwarded(self):
        async def go():
            o, a, log, *_, task = await started()
            n = len(a["codex"].sent)
            a["claude"].say("[[QUIET]]")
            await tick()
            self.assertEqual(len(a["codex"].sent), n)
            task.cancel()
        run(go())

    def test_mention_copies_other_agent(self):
        async def go():
            o, a, log, *_, task = await started()
            o.say("@codex push it")
            await tick()
            self.assertIn("[Saksham to you]: push it", a["codex"].sent)
            self.assertIn("[Saksham to Codex, so you know]: push it", a["claude"].sent)
            task.cancel()
        run(go())

    def test_plan_card_tells_them_to_wait_quietly(self):
        async def go():
            o, a, log, work, rd, task = await started()
            open(os.path.join(rd, "plan.md"), "w").write("- [ ] x")
            a["claude"].say("[[READY: plan]]"); a["codex"].say("[[READY: plan]]")
            await tick()
            self.assertTrue(any("wait" in s.lower() and "[[QUIET]]" in s for s in a["claude"].sent))
            task.cancel()
        run(go())
