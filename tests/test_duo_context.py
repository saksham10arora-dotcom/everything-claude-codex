import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from duo import context


class Context(unittest.TestCase):
    def brief(self, **env):
        with mock.patch.dict(os.environ, {"HOME": tempfile.mkdtemp(), **env}):
            return context.brief("Claude", "Codex", "fix the bug", "Saksham", "/w/.duo/r1")

    def test_brief_has_no_roles(self):
        b = self.brief(ECX_DUO_CONTEXT="").lower()
        for w in ("lead", "builder", "reviewer"):
            self.assertNotIn(w, b)

    def test_brief_mentions_both_signals_and_rules(self):
        b = self.brief(ECX_DUO_CONTEXT="")
        for s in ("[[READY: plan]]", "[[READY: done]]", "[Codex]", "[Saksham to you]", "[Saksham to both]",
                  "/w/.duo/r1/plan.md", "/w/.duo/r1/summary.md", "git add -A", "fix the bug"):
            self.assertIn(s, b)

    def test_brief_includes_context_file(self):
        f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
        f.write("SECRET-CONTEXT-LINE"); f.close()
        self.assertIn("SECRET-CONTEXT-LINE", self.brief(ECX_DUO_CONTEXT=f.name))

    def _fake_home(self):
        home = tempfile.mkdtemp()
        d = os.path.join(home, ".claude", "projects", "x")
        os.makedirs(d)
        now = datetime.now(timezone.utc).isoformat()
        with open(os.path.join(d, "s.jsonl"), "w") as f:
            for i in range(20):
                f.write(json.dumps({"type": "user", "timestamp": now,
                                    "message": {"role": "user", "content": f"hello number {i} " * 5}}) + "\n")
        return home

    def test_catchup_does_not_touch_cursors(self):
        home = self._fake_home()
        with mock.patch.dict(os.environ, {"HOME": home}):
            out = context.catchup()
        self.assertIn("hello number", out)
        self.assertFalse(os.path.exists(os.path.join(home, ".agent-sync")))

    def test_catchup_truncates(self):
        home = self._fake_home()
        with mock.patch.dict(os.environ, {"HOME": home}):
            out = context.catchup(limit_chars=100)
        self.assertLessEqual(len(out), 100)


if __name__ == "__main__":
    unittest.main()
