import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from duo.claude_agent import ClaudeAgent, parse_line, to_request

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "duo")


def frames():
    return [json.loads(l)["frame"] for l in open(os.path.join(FIX, "claude_probe.jsonl"))
            if json.loads(l)["dir"] == "in" and isinstance(json.loads(l)["frame"], dict)]


def kinds_of(pred):
    out = []
    for f in frames():
        if pred(f):
            out += [k for k, _ in parse_line(f)]
    return out


class Parse(unittest.TestCase):
    def test_parse_assistant_text_is_message(self):
        evs = [e for f in frames() for e in parse_line(f) if e[0] == "message"]
        self.assertTrue(any("DONE1" in d["text"] for _, d in evs))

    def test_parse_tool_use_is_tool(self):
        evs = [d for f in frames() for k, d in parse_line(f) if k == "tool"]
        self.assertIn("Write", [d["name"] for d in evs])
        self.assertTrue(all("detail" in d for d in evs))

    def test_empty_thinking_is_not_reasoning(self):
        self.assertNotIn("reasoning", [k for f in frames() for k, _ in parse_line(f)])
        self.assertEqual(parse_line({"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "hmm"}]}}),
                         [("reasoning", {"text": "hmm"})])

    def test_parse_result_ends_turn(self):
        self.assertIn("turn_end", kinds_of(lambda f: f.get("type") == "result"))

    def test_tool_result_parsed(self):
        self.assertIn("tool_result", kinds_of(lambda f: f.get("type") == "user"))

    def test_to_request_maps_tools(self):
        cases = [("Bash", {"command": "ls"}, "bash", {"command": "ls"}),
                 ("Write", {"file_path": "a"}, "write", {"path": "a"}),
                 ("Edit", {"file_path": "a"}, "edit", {"path": "a"}),
                 ("Read", {"file_path": "a"}, "read", {"path": "a"}),
                 ("WebFetch", {"url": "u"}, "web", {"url": "u"}),
                 ("mcp__gmail__send", {"to": "x"}, "mcp", {"name": "mcp__gmail__send", "args": {"to": "x"}})]
        for name, inp, tool, want in cases:
            r = to_request(name, inp)
            self.assertEqual((r.tool, r.input), (tool, want), name)


class Live(unittest.TestCase):
    def test_permission_roundtrip(self):
        out = tempfile.mktemp()
        env = {"ECX_DUO_CLAUDE_BIN": f"{sys.executable} {os.path.join(FIX, 'fake_claude.py')}", "FAKE_OUT": out}

        async def go():
            a = ClaudeAgent(tempfile.mkdtemp(), "sonnet", "medium")
            seen, ended = [], asyncio.Event()
            a.on_event = lambda k, d: seen.append(k)
            a.on_turn_end = ended.set

            async def approve(ap):
                seen.append(("approval", ap.request.tool, ap.summary))
                return "allow", ""
            a.on_approval = approve
            await a.start("BRIEF", "go")
            await asyncio.wait_for(ended.wait(), 10)
            await a.close()
            return seen

        with mock.patch.dict(os.environ, env):
            seen = asyncio.run(go())
        self.assertIn(("approval", "write", "write a.txt"), seen)
        self.assertIn("message", seen)
        sent = [json.loads(l) for l in open(out)]
        resp = [f for f in sent if f.get("type") == "control_response"][0]["response"]
        self.assertEqual(resp["request_id"], "perm-1")
        self.assertEqual(resp["response"]["behavior"], "allow")
        argv = sent[0]["argv"]
        for flag in ("--permission-prompt-tool", "--no-session-persistence", "--append-system-prompt-file"):
            self.assertIn(flag, argv)


if __name__ == "__main__":
    unittest.main()


class Summary(unittest.TestCase):
    def test_summary_unwraps_codex_shell(self):
        from duo.agents import summarize
        from duo.policy import Request
        self.assertEqual(summarize(Request("codex", "bash", {"command": "/bin/zsh -lc 'git push'"})), "git push")
