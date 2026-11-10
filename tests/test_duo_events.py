import json
import os
import tempfile
import unittest

from duo.events import EventLog


class Events(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "events.jsonl")
        self.log = EventLog(self.path)

    def test_add_appends_jsonl_with_increasing_seq(self):
        self.log.add("claude", "message", text="hi")
        self.log.add("codex", "message", text="yo")
        lines = [json.loads(l) for l in open(self.path)]
        self.assertEqual([e["seq"] for e in lines], [1, 2])
        self.assertEqual(lines[0]["agent"], "claude")
        self.assertEqual(lines[1]["text"], "yo")

    def test_since_returns_only_newer(self):
        for i in range(3):
            self.log.add("duo", "status", n=i)
        self.assertEqual([e["seq"] for e in self.log.since(1)], [2, 3])

    def test_subscriber_gets_new_events(self):
        q = self.log.subscribe()
        self.log.add("user", "message", text="go")
        self.assertEqual(q.get(timeout=1)["kind"], "message")

    def test_load_roundtrip(self):
        e = self.log.add("claude", "tool", name="Bash", detail="ls")
        self.assertEqual(EventLog.load(self.path), [e])

    def test_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            self.log.add("claude", "nonsense")


if __name__ == "__main__":
    unittest.main()
