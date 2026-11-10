import os
import tempfile
import unittest

from duo.policy import Ctx, Request, classify


def ctx(phase="build", **kw):
    w = kw.pop("workdir", WORK)
    return Ctx(workdir=w, phase=phase, existed=kw.get("existed", {os.path.join(w, "old.py")}),
               created=kw.get("created", {os.path.join(w, "new.py")}),
               protected=[os.path.expanduser("~/Downloads/yep")])


WORK = tempfile.mkdtemp()


def bash(cmd, **c):
    return classify(Request("claude", "bash", {"command": cmd}), ctx(**c))[0]


def tool(t, path, **c):
    return classify(Request("codex", t, {"path": path}), ctx(**c))[0]


class Policy(unittest.TestCase):
    def test_rm_rf_root_blocked(self):
        self.assertEqual(bash("rm -rf ~"), "block")

    def test_guard_ask_is_card(self):
        self.assertEqual(bash("sudo ls"), "card")

    def test_git_push_card(self):
        self.assertEqual(bash("git push origin duo/x"), "card")

    def test_curl_get_allowed(self):
        self.assertEqual(bash("curl https://example.com"), "allow")

    def test_curl_post_card(self):
        self.assertEqual(bash("curl -X POST https://example.com"), "card")
        self.assertEqual(bash("curl -d a=1 https://example.com"), "card")

    def test_codex_shell_wrapper_unwrapped(self):
        self.assertEqual(bash("/bin/zsh -lc 'curl -s -X POST https://example.com'"), "card")
        self.assertEqual(bash('/bin/zsh -lc "git push"'), "card")

    def test_gh_and_publish_card(self):
        for c in ("gh pr create", "npm publish", "vercel --prod", "twine upload dist/*", "scp a me@host:", "ssh me@host"):
            self.assertEqual(bash(c), "card", c)

    def test_global_install_card(self):
        self.assertEqual(bash("npm install -g left-pad"), "card")
        self.assertEqual(bash("brew install jq"), "card")
        self.assertEqual(bash("npm install left-pad"), "allow")

    def test_rm_existing_card_created_allowed(self):
        self.assertEqual(bash("rm old.py"), "card")
        self.assertEqual(bash("rm new.py"), "allow")
        self.assertEqual(bash("rm -r somedir"), "card")
        self.assertEqual(bash("git rm old.py"), "card")

    def test_plan_phase_blocks_edit(self):
        self.assertEqual(tool("edit", os.path.join(WORK, "old.py"), phase="plan"), "block")

    def test_plan_phase_allows_run_folder_notes(self):
        self.assertEqual(tool("write", os.path.join(WORK, ".duo", "r1", "plan.md"), phase="plan"), "allow")

    def test_plan_phase_bash_readonly_allowed_else_card(self):
        self.assertEqual(bash("git status", phase="plan"), "allow")
        self.assertEqual(bash("ls -la", phase="plan"), "allow")
        self.assertEqual(bash("python3 build.py", phase="plan"), "card")

    def test_existing_file_delete_card(self):
        self.assertEqual(tool("delete", os.path.join(WORK, "old.py")), "card")

    def test_created_file_delete_allowed(self):
        self.assertEqual(tool("delete", os.path.join(WORK, "new.py")), "allow")

    def test_write_existing_card(self):
        self.assertEqual(tool("write", os.path.join(WORK, "old.py")), "card")
        self.assertEqual(tool("write", os.path.join(WORK, "new.py")), "allow")
        self.assertEqual(tool("write", "brand_new.py"), "allow")  # relative to workdir

    def test_edit_existing_allowed(self):
        self.assertEqual(tool("edit", os.path.join(WORK, "old.py")), "allow")

    def test_outside_workdir_edit_card(self):
        self.assertEqual(tool("edit", "/etc/hosts"), "card")
        self.assertEqual(tool("write", os.path.join(WORK, "..", "escape.py")), "card")

    def test_mcp_send_card(self):
        r = classify(Request("claude", "mcp", {"name": "mcp__gmail__send_message", "args": {}}), ctx())
        self.assertEqual(r[0], "card")

    def test_mcp_search_allowed(self):
        r = classify(Request("codex", "mcp", {"name": "mcp__vault-rag__search_vault", "args": {}}), ctx())
        self.assertEqual(r[0], "allow")

    def test_protected_path_blocked_even_for_read(self):
        self.assertEqual(tool("read", os.path.expanduser("~/Downloads/yep/x")), "block")
        self.assertEqual(bash("ls ~/Downloads/yep"), "block")

    def test_browser_tools_card(self):
        r = classify(Request("claude", "mcp__claude-in-chrome__navigate", {"url": "x"}), ctx())
        self.assertEqual(r[0], "card")

    def test_unknown_tool_allowed(self):
        self.assertEqual(classify(Request("claude", "TodoWrite", {}), ctx())[0], "allow")

    def test_reason_given(self):
        self.assertTrue(classify(Request("claude", "bash", {"command": "git push"}), ctx())[1])


if __name__ == "__main__":
    unittest.main()
