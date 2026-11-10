import os
import tempfile
import unittest

from duo import report


def ev(seq, agent, kind, **d):
    return {"seq": seq, "ts": 1794300000 + seq, "agent": agent, "kind": kind, **d}


WORK = "/w"


class Report(unittest.TestCase):
    def test_audit_lists_denied_and_outward_first(self):
        events = [ev(1, "codex", "tool", name="shell", detail="curl -X POST https://x.io"),
                  ev(2, "duo", "card_open", id="c1", card="action", by="claude", summary="git push origin x", reason="pushes"),
                  ev(3, "user", "card_resolved", id="c1", decision="deny", note="no"),
                  ev(4, "duo", "blocked", by="claude", summary="rm -rf ~", reason="deletes your home"),
                  ev(5, "claude", "tool", name="mcp__gmail__send_message", detail="{}"),
                  ev(6, "codex", "file_change", paths=["/etc/hosts"], kinds=["update"], status="completed")]
        a = report.audit(events, WORK)
        first = a.split("## Every action")[0]
        for s in ("curl -X POST", "git push origin x", "denied", "rm -rf ~", "mcp__gmail__send_message", "/etc/hosts"):
            self.assertIn(s, first, s)

    def test_audit_none_when_clean(self):
        a = report.audit([ev(1, "claude", "tool", name="Read", detail="a.py")], WORK)
        self.assertIn("None.", a.split("## Every action")[0])

    def test_report_contains_every_tool_event(self):
        events = [ev(i, "claude", "tool", name="Bash", detail=f"step {i}") for i in range(1, 6)]
        a = report.audit(events, WORK)
        rows = [l for l in a.splitlines() if l.startswith("| ") and "step " in l]
        self.assertEqual(len(rows), 5)

    def test_pipes_escaped_in_table(self):
        a = report.audit([ev(1, "claude", "tool", name="Bash", detail="ls | wc -l")], WORK)
        self.assertIn("ls \\| wc -l", a)

    def test_report_without_summary(self):
        rd = tempfile.mkdtemp()
        p = report.write(rd, [ev(1, "duo", "status", status="running", goal="the goal")], tempfile.mkdtemp(), "stopped")
        text = open(p).read()
        self.assertIn("No summary was written.", text)
        self.assertIn("the goal", text)
        self.assertIn("the agents cannot edit it", text)

    def test_report_with_summary(self):
        rd = tempfile.mkdtemp()
        open(os.path.join(rd, "summary.md"), "w").write("We built the thing.")
        text = open(report.write(rd, [], tempfile.mkdtemp(), "done")).read()
        self.assertIn("We built the thing.", text)
        self.assertIn("written by the agents", text)


if __name__ == "__main__":
    unittest.main()
