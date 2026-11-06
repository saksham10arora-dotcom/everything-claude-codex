"""Tests for skills/catchup/catchup.py: fake session transcripts in a temp folder."""

import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

CATCHUP = os.path.join(os.path.dirname(__file__), "..", "skills", "catchup", "catchup.py")

_spec = importlib.util.spec_from_file_location("catchup", CATCHUP)
catchup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catchup)


def write_session(path, text, mtime):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {"type": "user", "message": {"content": text}}
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    os.utime(path, (mtime, mtime))


class CatchupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj-vault")
        now = time.time()
        # Newest file is the current session (the one /catchup was typed into).
        write_session(os.path.join(self.proj, "current.jsonl"), "current pineapple chat", now)
        write_session(os.path.join(self.proj, "older-a.jsonl"), "first topic about apples", now - 600)
        write_session(os.path.join(self.proj, "older-b.jsonl"), "second topic about pineapple", now - 1200)
        self._old_glob = catchup.PROJECT_GLOB
        catchup.PROJECT_GLOB = os.path.join(self.tmp, "proj*")

    def tearDown(self):
        catchup.PROJECT_GLOB = self._old_glob
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_main(self, *args):
        old_argv = sys.argv
        sys.argv = ["catchup.py", *args]
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                catchup.main()
        finally:
            sys.argv = old_argv
        return buf.getvalue()

    def test_list_skips_current_session(self):
        out = self.run_main("list")
        self.assertIn("Found 2 past session(s)", out)
        self.assertNotIn("current.jsonl", out)
        self.assertNotIn("current pineapple chat", out)
        self.assertIn("first topic about apples", out)
        self.assertIn("second topic about pineapple", out)

    def test_keyword_search_returns_only_matching_other_sessions(self):
        out = self.run_main("pineapple")
        self.assertIn("1 session(s) mention 'pineapple'", out)
        self.assertIn("second topic about pineapple", out)
        self.assertNotIn("first topic about apples", out)
        # The current session also mentions pineapple but must never be read back.
        self.assertNotIn("current pineapple chat", out)

    def test_default_reads_most_recent_other_session(self):
        out = self.run_main()
        self.assertIn("first topic about apples", out)
        self.assertNotIn("current pineapple chat", out)
        self.assertNotIn("second topic about pineapple", out)


if __name__ == "__main__":
    unittest.main()
