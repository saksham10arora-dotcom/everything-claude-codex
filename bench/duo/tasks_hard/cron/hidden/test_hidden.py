import unittest
from datetime import datetime as D
from cron import next_run


class Hidden(unittest.TestCase):
    def run_case(self, e, a, want): self.assertEqual(next_run(e, a), want, e)
    def test_weekday_hours(self): self.run_case("*/15 9-17 * * 1-5", D(2026, 11, 13, 17, 50), D(2026, 11, 16, 9, 0))
    def test_dom_or_dow(self): self.run_case("0 0 13 * fri", D(2026, 1, 1), D(2026, 1, 2))
    def test_dom_only(self): self.run_case("0 0 13 * *", D(2026, 1, 1), D(2026, 1, 13))
    def test_dow_only(self): self.run_case("0 0 * * fri", D(2026, 1, 1), D(2026, 1, 2))
    def test_list_or_dow(self): self.run_case("30 4 1,15 * 5", D(2026, 2, 1, 4, 30), D(2026, 2, 6, 4, 30))
    def test_feb_29(self): self.run_case("0 12 29 2 *", D(2026, 3, 1), D(2028, 2, 29, 12, 0))
    def test_month_range_step(self): self.run_case("0 0 * jan-mar/2 sun", D(2026, 1, 5), D(2026, 1, 11))
    def test_sunday_7(self): self.run_case("5 4 * * 7", D(2026, 11, 10, 12), D(2026, 11, 15, 4, 5))
    def test_sunday_0(self): self.run_case("5 4 * * 0", D(2026, 11, 10, 12), D(2026, 11, 15, 4, 5))
    def test_names_case(self): self.run_case("0 22 * * MON-fri", D(2026, 11, 10, 22), D(2026, 11, 11, 22))
    def test_range_step(self): self.run_case("0-10/5 * * * *", D(2026, 11, 10, 12, 10), D(2026, 11, 10, 13, 0))
    def test_month_name(self): self.run_case("10-12 3 * DEC *", D(2026, 11, 10), D(2026, 12, 1, 3, 10))
    def test_year_wrap(self): self.run_case("59 23 31 12 *", D(2026, 12, 31, 23, 59), D(2027, 12, 31, 23, 59))
    def test_31st(self): self.run_case("0 0 31 * *", D(2026, 4, 1), D(2026, 5, 31))
    def test_hour_step(self): self.run_case("15 */6 * * *", D(2026, 11, 10, 18, 15), D(2026, 11, 11, 0, 15))
    def test_seconds_dropped(self): self.run_case("* * * * *", D(2026, 1, 1, 10, 0, 30, 5), D(2026, 1, 1, 10, 1))
    def bad(self, e):
        with self.assertRaises(ValueError): next_run(e, D(2026, 1, 1))
    def test_bad_count(self): self.bad("* * * *")
    def test_bad_minute(self): self.bad("60 * * * *")
    def test_bad_hour(self): self.bad("* 24 * * *")
    def test_bad_step(self): self.bad("*/0 * * * *")
    def test_bad_range(self): self.bad("5-1 * * * *")
    def test_bad_name(self): self.bad("* * * foo *")
    def test_bad_dom(self): self.bad("* * 0 * *")
    def test_bad_dow(self): self.bad("* * * * 8")
