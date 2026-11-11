"""Structural tests for skills/standup/SKILL.md.

No Python helper exists for this skill (the agent reads the files directly),
so the tests verify that the skill file is well-formed and contains the
required sections and guard-rails.
"""

import os
import re
import unittest

SKILL = os.path.join(os.path.dirname(__file__), "..", "skills", "standup", "SKILL.md")


def _read():
    with open(SKILL, encoding="utf-8") as f:
        return f.read()


class StandupSkillStructure(unittest.TestCase):

    def setUp(self):
        self.text = _read()

    # ------------------------------------------------------------------
    # File exists
    # ------------------------------------------------------------------

    def test_skill_file_exists(self):
        self.assertTrue(os.path.isfile(SKILL), "skills/standup/SKILL.md must exist")

    # ------------------------------------------------------------------
    # Frontmatter
    # ------------------------------------------------------------------

    def test_frontmatter_name_is_standup(self):
        self.assertIn("name: standup", self.text)

    def test_frontmatter_has_description(self):
        self.assertRegex(self.text, r"description:.+standup", re.IGNORECASE)

    def test_frontmatter_triggers_on_standup_command(self):
        self.assertIn("/standup", self.text)

    # ------------------------------------------------------------------
    # Required output sections
    # ------------------------------------------------------------------

    def test_has_yesterday_section(self):
        self.assertIn("Yesterday", self.text)

    def test_has_today_section(self):
        self.assertIn("Today", self.text)

    def test_has_blockers_section(self):
        self.assertIn("Blockers", self.text)

    # ------------------------------------------------------------------
    # Source files referenced
    # ------------------------------------------------------------------

    def test_references_daily_notes(self):
        self.assertIn("daily/", self.text)

    def test_references_hot_md(self):
        self.assertIn("hot.md", self.text)

    # ------------------------------------------------------------------
    # No-invent guard-rail must be explicit
    # ------------------------------------------------------------------

    def test_no_invent_rule_stated(self):
        """The skill must explicitly forbid inventing items."""
        self.assertRegex(self.text, r"(never|Never)\s+invent", re.IGNORECASE)

    # ------------------------------------------------------------------
    # Missing-file behaviour must be specified
    # ------------------------------------------------------------------

    def test_missing_file_behaviour_specified(self):
        """Skill must say what to do when a daily note does not exist."""
        self.assertRegex(self.text, r"(missing|does not exist|No note)", re.IGNORECASE)


if __name__ == "__main__":
    unittest.main()
