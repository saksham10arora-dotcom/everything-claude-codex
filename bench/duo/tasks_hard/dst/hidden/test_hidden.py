import unittest
from datetime import datetime as D, timedelta, timezone
from dst import next_daily

U = timezone.utc
NY = "America/New_York"


class Hidden(unittest.TestCase):
    def check(self, h, m, tz, after, want): self.assertEqual(next_daily(h, m, tz, after), want)
    def test_plain(self): self.check(9, 0, NY, D(2026, 11, 10, 13, tzinfo=U), D(2026, 11, 10, 14, tzinfo=U))
    def test_spring_gap(self): self.check(2, 30, NY, D(2026, 3, 7, 12, tzinfo=U), D(2026, 3, 8, 7, tzinfo=U))
    def test_fall_first(self): self.check(1, 30, NY, D(2026, 10, 31, 12, tzinfo=U), D(2026, 11, 1, 5, 30, tzinfo=U))
    def test_fall_once(self): self.check(1, 30, NY, D(2026, 11, 1, 5, 31, tzinfo=U), D(2026, 11, 2, 6, 30, tzinfo=U))
    def test_kolkata(self): self.check(23, 59, "Asia/Kolkata", D(2026, 11, 10, 18, 29, tzinfo=U), D(2026, 11, 11, 18, 29, tzinfo=U))
    def test_half_hour_gap(self): self.check(2, 15, "Australia/Lord_Howe", D(2026, 10, 3, 12, tzinfo=U), D(2026, 10, 3, 15, 30, tzinfo=U))
    def test_london_gap(self): self.check(1, 15, "Europe/London", D(2026, 3, 28, 12, tzinfo=U), D(2026, 3, 29, 1, tzinfo=U))
    def test_london_fall(self): self.check(1, 15, "Europe/London", D(2026, 10, 24, 12, tzinfo=U), D(2026, 10, 25, 0, 15, tzinfo=U))
    def test_strictly_after(self): self.check(9, 0, NY, D(2026, 11, 10, 14, tzinfo=U), D(2026, 11, 11, 14, tzinfo=U))
    def test_other_zone_input(self):
        self.check(9, 0, NY, D(2026, 11, 10, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))), D(2026, 11, 10, 14, tzinfo=U))
    def test_returns_utc(self):
        self.assertEqual(next_daily(9, 0, NY, D(2026, 11, 10, 13, tzinfo=U)).utcoffset(), timedelta(0))
    def test_bad_zone(self):
        with self.assertRaises(ValueError): next_daily(9, 0, "Mars/Olympus", D(2026, 1, 1, tzinfo=U))
    def test_bad_hour(self):
        with self.assertRaises(ValueError): next_daily(24, 0, NY, D(2026, 1, 1, tzinfo=U))
    def test_bad_minute(self):
        with self.assertRaises(ValueError): next_daily(9, 60, NY, D(2026, 1, 1, tzinfo=U))
