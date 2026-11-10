import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from duo.codex_agent import CodexAgent, approval_to_request, codex_home, mcp_servers, parse_notification

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "duo")


def notes(name):
    for l in open(os.path.join(FIX, name)):
        f = json.loads(l)["frame"]
        if isinstance(f, dict) and "method" in f and "id" not in f:
            yield f["method"], f.get("params", {})


def kinds(name):
    return [k for m, p in notes(name) for k, _ in parse_notification(m, p)]


class Parse(unittest.TestCase):
    def test_agent_message_completed_is_message(self):
        evs = [d for m, p in notes("codex_probe.jsonl") for k, d in parse_notification(m, p) if k == "message"]
        self.assertTrue(any("DONE1" in d["text"] for d in evs))

    def test_command_item_is_tool(self):
        evs = [d for m, p in notes("codex_probe.jsonl") for k, d in parse_notification(m, p) if k == "tool"]
        self.assertTrue(any("curl" in d["detail"] for d in evs))
        self.assertFalse(any(d["detail"].startswith("/bin/zsh") for d in evs))

    def test_mcp_call_is_tool(self):
        evs = [d for m, p in notes("codex_probe.jsonl") for k, d in parse_notification(m, p) if k == "tool"]
        self.assertIn("mcp__cua_repl__js", [d["name"] for d in evs])

    def test_turn_completed_ends_turn(self):
        self.assertIn("turn_end", kinds("codex_probe.jsonl"))

    def test_reasoning_summary_is_reasoning(self):
        self.assertEqual(parse_notification("item/completed", {"item": {"type": "reasoning", "summary": ["thinking it over"]}}),
                         [("reasoning", {"text": "thinking it over"})])
        self.assertEqual(parse_notification("item/completed", {"item": {"type": "reasoning", "summary": []}}), [])

    def test_file_change_delete_maps_to_delete(self):
        items = {"fc1": {"type": "fileChange", "changes": [{"path": "/w/a.py", "kind": {"type": "delete"}},
                                                           {"path": "/w/b.py", "kind": {"type": "add"}},
                                                           {"path": "/w/c.py", "kind": {"type": "update"}}]}}
        reqs = approval_to_request("item/fileChange/requestApproval", {"itemId": "fc1"}, items)
        self.assertEqual([(r.tool, r.input["path"]) for r in reqs], [("delete", "/w/a.py"), ("write", "/w/b.py"), ("edit", "/w/c.py")])

    def test_command_and_mcp_approvals_map(self):
        r = approval_to_request("item/commandExecution/requestApproval", {"command": "/bin/zsh -lc 'git push'"}, {})
        self.assertEqual((r[0].tool, r[0].input["command"]), ("bash", "/bin/zsh -lc 'git push'"))
        r = approval_to_request("mcpServer/elicitation/request", {
            "serverName": "gmail", "message": 'Allow the gmail MCP server to run tool "send_message"?',
            "_meta": {"codex_approval_kind": "mcp_tool_call", "tool_params": "{'to': 'x'}"}}, {})
        self.assertEqual((r[0].tool, r[0].input["name"]), ("mcp", "mcp__gmail__send_message"))

    def test_mcp_servers_read_from_config(self):
        f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        f.write('model = "x"\n[mcp_servers.alpha]\ncommand="a"\n[mcp_servers.alpha.env]\nK="v"\n[mcp_servers.beta-2]\n')
        f.close()
        self.assertEqual(mcp_servers(f.name), ["alpha", "beta-2"])

    def test_codex_home_links_login_not_rules(self):
        real, home = tempfile.mkdtemp(), tempfile.mkdtemp()
        for n in ("auth.json", "config.toml", "AGENTS.md"):
            open(os.path.join(real, n), "w").write("x")
        os.makedirs(os.path.join(real, "rules")); os.makedirs(os.path.join(real, "sessions"))
        h = codex_home(real, os.path.join(home, "duo-home"))
        self.assertEqual(sorted(os.listdir(h)), ["AGENTS.md", "auth.json", "config.toml"])
        self.assertTrue(os.path.islink(os.path.join(h, "auth.json")))


class Live(unittest.TestCase):
    def test_first_turn_starts_even_if_marked_busy(self):
        out, work = tempfile.mktemp(), os.path.realpath(tempfile.mkdtemp())
        env = {"ECX_DUO_CODEX_BIN": f"{sys.executable} {os.path.join(FIX, 'fake_codex.py')}", "FAKE_OUT": out,
               "ECX_DUO_CODEX_HOME": os.path.join(tempfile.mkdtemp(), "h")}

        async def go():
            a = CodexAgent(work, None, "medium")
            ended = asyncio.Event()
            a.on_turn_end = ended.set

            async def approve(ap):
                return "allow", ""
            a.on_approval = approve
            a.busy = True  # what the orchestrator used to do before start
            await a.start("BRIEF", "go")
            await asyncio.wait_for(ended.wait(), 10)
            await a.close()

        with mock.patch.dict(os.environ, env):
            asyncio.run(go())
        self.assertIn("turn/start", [json.loads(l).get("method") for l in open(out)])

    def test_steer_used_when_busy_and_thread_is_ephemeral(self):
        out, work = tempfile.mktemp(), os.path.realpath(tempfile.mkdtemp())
        env = {"ECX_DUO_CODEX_BIN": f"{sys.executable} {os.path.join(FIX, 'fake_codex.py')}", "FAKE_OUT": out,
               "ECX_DUO_CODEX_HOME": os.path.join(tempfile.mkdtemp(), "h")}

        async def go():
            a = CodexAgent(work, None, "medium")
            seen, ended = [], asyncio.Event()
            a.on_event = lambda k, d: seen.append((k, d))
            a.on_turn_end = ended.set

            async def approve(ap):
                seen.append(("approval", ap.request.tool, ap.request.input.get("path")))
                await a.send("steer me")
                return "deny", "no"
            a.on_approval = approve
            await a.start("BRIEF", "go")
            await asyncio.wait_for(ended.wait(), 10)
            await a.close()
            return seen

        with mock.patch.dict(os.environ, env):
            seen = asyncio.run(go())
        self.assertIn(("approval", "delete", os.path.join(work, "old.py")), seen)
        self.assertIn("hello from codex", [e[1].get("text") for e in seen if e[0] == "message"])
        sent = [json.loads(l) for l in open(out)]
        methods = [f.get("method") for f in sent]
        self.assertIn("turn/steer", methods)
        ts = [f for f in sent if f.get("method") == "thread/start"][0]["params"]
        self.assertTrue(ts["ephemeral"])
        self.assertEqual(ts["approvalPolicy"], "untrusted")
        self.assertEqual(ts["developerInstructions"], "BRIEF")
        self.assertEqual([f for f in sent if f.get("id") == 100][0]["result"], {"decision": "decline"})
        self.assertIn("features.codex_hooks=false", sent[0]["argv"])
        self.assertIn("features.plugins=false", sent[0]["argv"])  # plugin MCP servers cannot be gated
        self.assertEqual(sent[0]["codex_home"], env["ECX_DUO_CODEX_HOME"])


if __name__ == "__main__":
    unittest.main()
