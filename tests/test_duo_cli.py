import os
import subprocess
import tempfile
import unittest
from unittest import mock

from duo import duo as cli


def repo():
    d = os.path.realpath(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q", d], check=True)
    open(os.path.join(d, "a.py"), "w").write("x = 1\n")
    subprocess.run(["git", "-C", d, "add", "."], check=True)
    subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"], check=True)
    return d


class Cli(unittest.TestCase):
    def setUp(self):
        self.which = mock.patch("shutil.which", return_value="/usr/bin/x")
        self.which.start()

    def tearDown(self):
        self.which.stop()

    def test_preflight_clean_repo_ok(self):
        with mock.patch.dict(os.environ, {"ECX_VAULT": ""}):
            self.assertEqual(cli.preflight(repo()), [])

    def test_preflight_dirty_tree(self):
        d = repo()
        open(os.path.join(d, "a.py"), "w").write("x = 2\n")
        with mock.patch.dict(os.environ, {"ECX_VAULT": ""}):
            self.assertTrue(any("Commit or stash" in p for p in cli.preflight(d)))

    def test_preflight_ignores_run_folder(self):
        d = repo()
        os.makedirs(os.path.join(d, ".duo", "r1"))
        open(os.path.join(d, ".duo", "r1", "events.jsonl"), "w").write("{}")
        cli.add_exclude(d)
        with mock.patch.dict(os.environ, {"ECX_VAULT": ""}):
            self.assertEqual(cli.preflight(d), [])

    def test_preflight_refuses_vault(self):
        d = repo()
        with mock.patch.dict(os.environ, {"ECX_VAULT": d}):
            self.assertTrue(any("vault" in p for p in cli.preflight(d)))

    def test_preflight_not_a_repo(self):
        with mock.patch.dict(os.environ, {"ECX_VAULT": ""}):
            self.assertIn(cli.NOT_GIT, cli.preflight(tempfile.mkdtemp()))

    def test_slug(self):
        self.assertEqual(cli.slug("Fix the failing login test now please"), "fix-the-failing-login-test")
        self.assertEqual(cli.slug("!!!"), "run")

    def test_exclude_added_once(self):
        d = repo()
        cli.add_exclude(d); cli.add_exclude(d)
        lines = open(os.path.join(d, ".git", "info", "exclude")).read().splitlines()
        self.assertEqual(lines.count(".duo/"), 1)

    def test_allow_rules_warning(self):
        d = repo()
        os.makedirs(os.path.join(d, ".claude"))
        open(os.path.join(d, ".claude", "settings.json"), "w").write('{"permissions": {"allow": ["Bash(git push:*)"]}}')
        self.assertTrue(any("git push" in w for w in cli.allow_rule_warnings(d)))

    def test_snapshot_has_tracked_files(self):
        d = repo()
        open(os.path.join(d, "untracked.txt"), "w").write("u")
        snap = cli.snapshot(d)
        self.assertIn(os.path.join(d, "a.py"), snap)
        self.assertIn(os.path.join(d, "untracked.txt"), snap)

    def test_protected_from_env(self):
        with mock.patch.dict(os.environ, {"ECX_PROTECTED": "~/a:/b"}):
            self.assertEqual(cli.protected_paths(), [os.path.expanduser("~/a"), "/b"])
        with mock.patch.dict(os.environ, {"ECX_PROTECTED": ""}):
            self.assertEqual(cli.protected_paths(), [])


if __name__ == "__main__":
    unittest.main()
