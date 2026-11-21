"""The install count is opt-in, counts once per machine, and never breaks an install."""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts import install

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


class CountInstall(unittest.TestCase):
    def setUp(self):
        self.marker = os.path.join(tempfile.mkdtemp(), ".ecx", "counted")
        install.DRY = False

    def tearDown(self):
        install.DRY = False

    def test_counts_once_per_machine(self):
        calls = []

        def opener(url, timeout):
            calls.append(url)
            return mock.Mock(read=lambda n: b"")

        self.assertTrue(install.count_install(self.marker, opener))
        self.assertFalse(install.count_install(self.marker, opener))
        self.assertEqual(calls, [install.COUNT_URL])

    def test_dry_run_sends_nothing(self):
        install.DRY = True
        self.assertFalse(install.count_install(self.marker, lambda *a, **k: self.fail("network call in dry run")))
        self.assertFalse(os.path.exists(self.marker))

    def test_offline_never_fails_and_retries_next_time(self):
        def offline(*a, **k):
            raise OSError("no network")

        self.assertFalse(install.count_install(self.marker, offline))
        self.assertFalse(os.path.exists(self.marker))

    def test_installer_does_not_count_without_the_flag(self):
        home = tempfile.mkdtemp()
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "install.py"),
                              "--vault", os.path.join(home, "vault"), "--name", "Ada"],
                             env={**os.environ, "HOME": home}, check=True, capture_output=True, text=True).stdout
        self.assertNotIn("Install count", out)
        self.assertFalse(os.path.exists(os.path.join(home, ".ecx", "counted")))

    def test_dry_run_with_the_flag_only_reports(self):
        home = tempfile.mkdtemp()
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "install.py"),
                              "--vault", os.path.join(home, "vault"), "--name", "Ada", "--dry-run", "--count-install"],
                             env={**os.environ, "HOME": home}, check=True, capture_output=True, text=True).stdout
        self.assertIn("would count this install", out)
        self.assertFalse(os.path.exists(os.path.join(home, ".ecx", "counted")))


if __name__ == "__main__":
    unittest.main()
