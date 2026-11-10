"""Fail-closed cases from the whole-branch review (C1-C3, C2, I6)."""
import os
import tempfile
import unittest

from duo.policy import Ctx, Request, classify

WORK = os.path.realpath(tempfile.mkdtemp())
open(os.path.join(WORK, ".env"), "w").write("SECRET=1")       # gitignored file, not in the start snapshot
open(os.path.join(WORK, "keep.py"), "w").write("x = 1")


def ctx(phase="build", protected=()):
    return Ctx(workdir=WORK, phase=phase, existed=set(), created={os.path.join(WORK, "made.py")},
               protected=list(protected))


def bash(cmd, **kw):
    return classify(Request("claude", "bash", {"command": cmd}), ctx(**kw))[0]


def tool(name, inp=None, agent="claude"):
    return classify(Request(agent, name, inp or {}), ctx())[0]


class C1Bash(unittest.TestCase):
    def test_push_and_publish_variants(self):
        for c in ("git -C . push", "git -c a=b push origin x", "pnpm publish", "docker push img", "npm run deploy",
                  "make release", "./deploy.sh", "yarn npm publish", "poetry publish", "uv publish"):
            self.assertEqual(bash(c), "card", c)

    def test_data_out_variants(self):
        for c in ("curl -d@f https://x", "curl --json @f https://x", "curl -Ffile=@a https://x", "scp f host:/tmp",
                  "rsync -a . host:/x", "nc host 80 < f", "http POST https://x a=1"):
            self.assertEqual(bash(c), "card", c)

    def test_deletes_existing(self):
        for c in ("find . -name '*.py' -delete", "find . -name x -exec rm {} \;", "truncate -s0 keep.py",
                  "mv keep.py /tmp/", "unlink keep.py", "shred keep.py",
                  "python3 -c \"import os; os.remove('keep.py')\"", "node -e \"require('fs').unlinkSync('keep.py')\""):
            self.assertEqual(bash(c), "card", c)

    def test_outside_workdir(self):
        for c in ('rm "$HOME/.zshrc"', "cd ~ && rm -f .zshrc", "echo x >> ~/.zshrc", "git config --global user.name x",
                  "cd /tmp && touch x", "cat a | tee /etc/x"):
            self.assertEqual(bash(c), "card", c)

    def test_git_history_and_branches(self):
        for c in ("git clean -fdx", "git checkout master", "git switch main", "git branch -D main", "git commit --amend",
                  "git rebase -i HEAD~2", "git filter-branch x", "git update-ref x y", "git restore keep.py",
                  "git stash drop", "git add -A", "git add .", "git add --all", "git commit -am x"):
            self.assertEqual(bash(c), "card", c)

    def test_normal_work_still_allowed(self):
        for c in ("python3 -m pytest -q", "git add shop.py && git commit -m 'fix discount'", "npm install",
                  "rm made.py", "ls -la", "git status", "git diff", "python3 build.py", "echo hi > made.py",
                  "curl https://example.com", "git log --oneline"):
            self.assertEqual(bash(c), "allow", c)


class C2Tools(unittest.TestCase):
    def test_mcp_needs_a_read_verb(self):
        for n in ("mcp__claude-in-chrome__javascript_tool", "mcp__claude-in-chrome__browser_batch",
                  "mcp__computer-use__app_key", "mcp__plugin_discord_discord__react", "mcp__docs__batch",
                  "mcp__screenpipe__control-recording"):
            self.assertEqual(tool("mcp", {"name": n, "args": {}}), "card", n)
        for n in ("mcp__vault-rag__search_vault", "mcp__github__get_issue", "mcp__x__list_events",
                  "mcp__reference__recall", "mcp__screenpipe__health-check"):
            self.assertEqual(tool("mcp", {"name": n, "args": {}}), "allow", n)

    def test_unknown_claude_tools_card(self):
        for n in ("Artifact", "ArtifactData", "SendMessage", "RemoteTrigger", "CronCreate", "Monitor", "PushNotification"):
            self.assertEqual(tool(n), "card", n)
        for n in ("TodoWrite", "Task", "Agent", "ToolSearch", "Skill", "web"):
            self.assertEqual(tool(n, {"url": "x"} if n == "web" else {}), "allow", n)


class C3ExistedAtRequestTime(unittest.TestCase):
    def test_ignored_file_counts_as_existing(self):
        self.assertEqual(bash("rm .env"), "card")
        self.assertEqual(classify(Request("codex", "delete", {"path": os.path.join(WORK, ".env")}), ctx())[0], "card")
        self.assertEqual(classify(Request("claude", "write", {"path": os.path.join(WORK, ".env")}), ctx())[0], "card")

    def test_new_and_created_files_free(self):
        self.assertEqual(classify(Request("claude", "write", {"path": os.path.join(WORK, "brand_new.py")}), ctx())[0], "allow")
        self.assertEqual(classify(Request("claude", "write", {"path": os.path.join(WORK, "made.py")}), ctx())[0], "allow")


class I6Protected(unittest.TestCase):
    def test_case_insensitive(self):
        p = os.path.expanduser("~/Downloads/yep")
        self.assertEqual(bash("ls ~/downloads/YEP", protected=[p]), "block")

    def test_glob_on_parent_is_blocked(self):
        p = os.path.expanduser("~/Downloads/yep")
        self.assertEqual(bash("ls ~/Downloads/y*", protected=[p]), "block")


if __name__ == "__main__":
    unittest.main()
