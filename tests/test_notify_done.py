"""notify_done.py: ECX_QUIET_HOURS window parsing and the quiet-hours check."""

import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))

from notify_done import in_quiet_hours, parse_quiet_hours  # noqa: E402


def at(hour):
    return datetime(2026, 1, 1, hour, 30)


class ParseQuietHours(unittest.TestCase):
    def test_valid_window(self):
        self.assertEqual(parse_quiet_hours("23-7"), (23, 7))

    def test_unset_or_bad_values_are_ignored(self):
        for value in [None, "", "abc", "23", "23-", "-7", "24-7", "7-25", "23:00-07:00", "-1-7"]:
            with self.subTest(value=value):
                self.assertIsNone(parse_quiet_hours(value))


class InQuietHours(unittest.TestCase):
    def test_wrap_around_midnight(self):
        self.assertTrue(in_quiet_hours("23-7", at(23)))
        self.assertTrue(in_quiet_hours("23-7", at(0)))
        self.assertTrue(in_quiet_hours("23-7", at(2)))
        self.assertFalse(in_quiet_hours("23-7", at(7)))
        self.assertFalse(in_quiet_hours("23-7", at(12)))

    def test_same_day_window(self):
        self.assertTrue(in_quiet_hours("9-17", at(9)))
        self.assertFalse(in_quiet_hours("9-17", at(17)))
        self.assertFalse(in_quiet_hours("9-17", at(8)))

    def test_bad_or_unset_value_never_silences(self):
        self.assertFalse(in_quiet_hours(None, at(2)))
        self.assertFalse(in_quiet_hours("nonsense", at(2)))


if __name__ == "__main__":
    unittest.main()
