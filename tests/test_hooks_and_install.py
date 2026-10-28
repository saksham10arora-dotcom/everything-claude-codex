"""Hooks get the real Claude Code payload on stdin; the installer runs in a temp HOME."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOOKS = os.path.join(ROOT, "hooks")


def run(script, payload, env=None, shell="python"):
    args = script if isinstance(script, list) else [script]
    cmd = [sys.executable, *args] if shell == "python" else ["bash", *args]
    out = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True,
                         env={**os.environ, **(env or {})})
    return out.stdout.strip()


def decision(command):
    out = run(os.path.join(HOOKS, "guard_dangerous.py"), {"tool_name": "Bash", "tool_input": {"command": command}})
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"


class Guard(unittest.TestCase):
    def test_blocks_catastrophic(self):
        for c in ("rm -rf /", "rm -rf ~", "sudo rm -rf / --no-preserve-root", "mkfs.ext4 /dev/sda1", "chmod -R 777 /"):
            self.assertEqual(decision(c), "deny", c)

    def test_asks_before_risky(self):
        for c in ("rm -rf build", "git push --force origin main", "git reset --hard HEAD~3", "DROP TABLE users;"):
            self.assertEqual(decision(c), "ask", c)

    def test_allows_normal(self):
        for c in ("ls -la", "npm test", "git push origin main", "python3 -m pytest"):
            self.assertEqual(decision(c), "allow", c)


class Hooks(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp()
        for d in (".remember", "inbox", "content"):
            os.makedirs(os.path.join(self.vault, d))
        self.env = {"ECX_VAULT": self.vault}

    def test_session_context_injects_hot(self):
        open(os.path.join(self.vault, ".remember", "hot.md"), "w").write("## WHO\nAda, builds robots\n")
        out = json.loads(run(os.path.join(HOOKS, "session_context.sh"), {}, self.env, "bash"))
        self.assertIn("Ada, builds robots", out["hookSpecificOutput"]["additionalContext"])

    def test_inbox_nudge_lists_files(self):
        open(os.path.join(self.vault, "inbox", "met-adi.md"), "w").write("met Adi")
        out = json.loads(run(os.path.join(HOOKS, "inbox_nudge.sh"), {}, self.env, "bash"))
        self.assertIn("met-adi.md", out["hookSpecificOutput"]["additionalContext"])

    def test_archive_moves_now_into_today(self):
        now = os.path.join(self.vault, ".remember", "now.md")
        open(now, "w").write("## 10:00\nshipped it\n")
        run(os.path.join(HOOKS, "archive_now.sh"), {}, self.env, "bash")
        self.assertEqual(os.path.getsize(now), 0)
        today = [f for f in os.listdir(os.path.join(self.vault, ".remember")) if f.startswith("today-")]
        self.assertEqual(len(today), 1)

    def test_ai_tell_guard_flags_em_dash(self):
        post = os.path.join(self.vault, "content", "post.md")
        open(post, "w").write("fast \u2014 and cheap")
        out = run(os.path.join(HOOKS, "ai_tell_guard.sh"), {"tool_input": {"file_path": post}}, self.env, "bash")
        self.assertIn("em dash", out)

    def test_auto_allow_reads_only(self):
        allowed = run(os.path.join(HOOKS, "auto_allow_reads.py"), {"tool_name": "Read"})
        self.assertEqual(json.loads(allowed)["hookSpecificOutput"]["decision"]["behavior"], "allow")
        self.assertEqual(run(os.path.join(HOOKS, "auto_allow_reads.py"), {"tool_name": "Write"}), "")


class McpHealthAndUsage(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.env = {"HOME": self.home}

    def test_mcp_blocks_after_two_failures_then_recovers(self):
        script = os.path.join(HOOKS, "mcp_health.py")
        call = {"tool_name": "mcp__flaky__search", "error": "500 boom"}
        self.assertEqual(run([script, "pre"], call, self.env), "")
        run([script, "fail"], call, self.env)
        run([script, "fail"], call, self.env)
        out = json.loads(run([script, "pre"], call, self.env))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("500 boom", out["hookSpecificOutput"]["permissionDecisionReason"])
        run([script, "ok"], call, self.env)
        self.assertEqual(run([script, "pre"], call, self.env), "")

    def test_usage_tracker_counts_each_message_once(self):
        transcript = os.path.join(self.home, "t.jsonl")
        usage = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 1}
        with open(transcript, "w") as f:
            for _ in range(3):  # one message is logged once per content block, same usage each time
                f.write(json.dumps({"type": "assistant", "message": {"id": "m1", "model": "claude-x", "usage": usage}}) + "\n")
        run(os.path.join(HOOKS, "usage_tracker.py"), {"session_id": "s1", "transcript_path": transcript, "cwd": "/p/demo"}, self.env)
        with open(os.path.join(self.home, ".claude", "metrics", "usage.jsonl")) as f:
            row = json.loads(f.read().splitlines()[-1])
        self.assertEqual(row["models"]["claude-x"]["output_tokens"], 5)
        self.assertEqual(row["models"]["claude-x"]["messages"], 1)


class Install(unittest.TestCase):
    def test_install_is_idempotent_and_doctor_passes(self):
        home = tempfile.mkdtemp()
        vault = os.path.join(home, "my vault")
        env = {**os.environ, "HOME": home}
        args = [sys.executable, os.path.join(ROOT, "scripts", "install.py"), "--vault", vault, "--name", "Ada"]
        subprocess.run(args, env=env, check=True, capture_output=True)
        second = subprocess.run(args, env=env, check=True, capture_output=True, text=True).stdout
        self.assertIn("0 global hooks added", second)
        self.assertIn("0 vault hooks added", second)
        with open(os.path.join(home, ".claude", "settings.json")) as f:
            groups = json.load(f)["hooks"]["PreToolUse"]
        self.assertEqual(sum("guard_dangerous" in h["command"] for g in groups for h in g["hooks"]), 1)
        doctor = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "doctor.py"), "--vault", vault],
                                env=env, capture_output=True, text=True)
        self.assertEqual(doctor.returncode, 0, doctor.stdout)


if __name__ == "__main__":
    unittest.main()
