"""statusline.sh: colour by default, none when NO_COLOR is set (https://no-color.org)."""

import json
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "statusline", "statusline.sh")
ESC = "\x1b["


def run(no_color=None):
    """Run the script on a 42% context sample, with one unread mail from Codex."""
    with tempfile.TemporaryDirectory() as home:
        sync = os.path.join(home, ".agent-sync")
        os.makedirs(sync)
        with open(os.path.join(sync, "mail.jsonl"), "w") as fh:
            fh.write(json.dumps({"id": 1, "to": "claude"}) + "\n")
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        env["HOME"] = home
        if no_color is not None:
            env["NO_COLOR"] = no_color
        result = subprocess.run(
            ["bash", SCRIPT],
            input=json.dumps({"context_window": {"used_percentage": 42}}) + "\n",
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
    return result.stdout


class StatusLineColour(unittest.TestCase):
    def test_colours_the_bar_and_the_mail_count_by_default(self):
        out = run()
        self.assertIn("ctx [████░░░░░░] 42%", out)
        self.assertIn("✉ 1 from Codex", out)
        self.assertIn(ESC, out)

    def test_no_color_prints_the_same_text_without_escape_codes(self):
        out = run("1")
        self.assertNotIn(ESC, out)
        self.assertEqual(out, "ctx [████░░░░░░] 42%  ·  ✉ 1 from Codex")

    def test_an_empty_no_color_keeps_the_colours(self):
        self.assertIn(ESC, run(""))


if __name__ == "__main__":
    unittest.main()
