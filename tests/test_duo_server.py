import json
import os
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

from duo.events import EventLog
from duo.server import start_server


class FakeOrch:
    def __init__(self):
        self.calls = []

    def say(self, text):
        self.calls.append(("say", text))

    def resolve_card(self, cid, decision, note=""):
        self.calls.append(("card", cid, decision, note))

    def control(self, action):
        self.calls.append(("control", action))


class Server(unittest.TestCase):
    def setUp(self):
        self.rd = tempfile.mkdtemp()
        self.log = EventLog(os.path.join(self.rd, "events.jsonl"))
        self.orch = FakeOrch()
        self.url, self.stop = start_server(self.log, self.orch, self.rd)
        q = urllib.parse.urlparse(self.url)
        self.base = f"{q.scheme}://{q.netloc}"
        self.token = urllib.parse.parse_qs(q.query)["t"][0]

    def tearDown(self):
        self.stop()

    def get(self, path, token=True):
        sep = "&" if "?" in path else "?"
        return urllib.request.urlopen(self.base + path + (f"{sep}t={self.token}" if token else ""), timeout=5)

    def post(self, path, body, token=True):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **({"X-Duo-Token": self.token} if token else {})})
        return urllib.request.urlopen(req, timeout=5)

    def test_requires_token(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/", token=False)
        self.assertEqual(e.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.post("/say", {"text": "hi"}, token=False)
        self.assertEqual(e.exception.code, 403)
        self.assertEqual(self.orch.calls, [])

    def test_index_served(self):
        self.assertIn(b"<html", self.get("/").read())

    def test_say_calls_orchestrator(self):
        self.post("/say", {"text": "@codex go"})
        self.assertEqual(self.orch.calls, [("say", "@codex go")])

    def test_card_post_resolves(self):
        self.post("/card", {"id": "c1", "decision": "deny", "note": "no"})
        self.assertEqual(self.orch.calls, [("card", "c1", "deny", "no")])

    def test_control_validated(self):
        self.post("/control", {"action": "pause"})
        with self.assertRaises(urllib.error.HTTPError):
            self.post("/control", {"action": "explode"})
        self.assertEqual(self.orch.calls, [("control", "pause")])

    def test_events_replay_since(self):
        for i in range(3):
            self.log.add("claude", "message", text=f"m{i}")
        r = self.get("/events?since=1")
        lines = []
        deadline = time.time() + 3
        while len(lines) < 2 and time.time() < deadline:
            line = r.readline().decode()
            if line.startswith("data: "):
                lines.append(json.loads(line[6:]))
        self.assertEqual([e["seq"] for e in lines], [2, 3])
        r.close()

    def test_plan_endpoint(self):
        open(os.path.join(self.rd, "plan.md"), "w").write("- [ ] a")
        self.assertEqual(self.get("/plan").read().decode(), "- [ ] a")

    def test_binds_localhost_only(self):
        self.assertTrue(self.url.startswith("http://127.0.0.1:"))


if __name__ == "__main__":
    unittest.main()
