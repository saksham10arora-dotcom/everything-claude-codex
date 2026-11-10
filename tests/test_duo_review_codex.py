"""Codex findings from the whole-branch review (I1, I7, I8)."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from duo.codex_agent import CodexAgent, approval_to_request
from duo.policy import Ctx, classify

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "duo")


def env(**extra):
    return {"ECX_DUO_CODEX_BIN": f"{sys.executable} {os.path.join(FIX, 'fake_codex.py')}", "FAKE_OUT": tempfile.mktemp(),
            "ECX_DUO_CODEX_HOME": os.path.join(tempfile.mkdtemp(), "h"), **extra}


class Patches(unittest.TestCase):
    def test_unknown_patch_paths_get_a_card(self):
        work = os.path.realpath(tempfile.mkdtemp())
        reqs = approval_to_request("item/fileChange/requestApproval", {"itemId": "missing"}, {})
        self.assertEqual(classify(reqs[0], Ctx(workdir=work, phase="build"))[0], "card")

    def test_move_path_is_delete_plus_write(self):
        items = {"i": {"changes": [{"path": "/w/a.py", "kind": {"type": "update", "move_path": "/w/b.py"}}]}}
        reqs = approval_to_request("item/fileChange/requestApproval", {"itemId": "i"}, items)
        self.assertEqual([(r.tool, r.input["path"]) for r in reqs], [("delete", "/w/a.py"), ("write", "/w/b.py")])


class Live(unittest.TestCase):
    def test_turn_start_failure_resets_busy(self):
        e = env(FAKE_FAIL_TURN="1")

        async def go():
            a = CodexAgent(os.path.realpath(tempfile.mkdtemp()), None, "medium")
            seen = []
            a.on_event = lambda k, d: seen.append((k, d))
            with self.assertRaises(RuntimeError):
                await a.start("BRIEF", "go")
            self.assertFalse(a.busy)
            await a.close()
            return seen
        with mock.patch.dict(os.environ, e):
            asyncio.run(go())

    def test_unlisted_mcp_servers_get_prompt_mode(self):
        e = env(FAKE_MCP="from_project_config")

        async def go():
            a = CodexAgent(os.path.realpath(tempfile.mkdtemp()), None, "medium")
            ended = asyncio.Event()
            a.on_turn_end = ended.set

            async def approve(ap):
                return "deny", ""
            a.on_approval = approve
            await a.start("BRIEF", "go")
            await asyncio.wait_for(ended.wait(), 10)
            await a.close()
        with mock.patch.dict(os.environ, e):
            asyncio.run(go())
        starts = [json.loads(l)["argv"] for l in open(e["FAKE_OUT"]) if '"argv"' in l]
        self.assertTrue(any('mcp_servers.from_project_config.default_tools_approval_mode="prompt"' in argv
                            for argv in starts), starts)


if __name__ == "__main__":
    unittest.main()
