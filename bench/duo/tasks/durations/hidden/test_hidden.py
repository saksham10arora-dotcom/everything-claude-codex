import unittest
from durations import parse_duration


class Hidden(unittest.TestCase):
    def test_joined(self): self.assertEqual(parse_duration("1h30m"), 5400)
    def test_days(self): self.assertEqual(parse_duration("2d"), 172800)
    def test_all(self): self.assertEqual(parse_duration("1d2h3m4s"), 93784)
    def test_case_and_space(self): self.assertEqual(parse_duration("  2H  "), 7200)
    def test_zero(self): self.assertEqual(parse_duration("0s"), 0)
    def bad(self, s):
        with self.assertRaises(ValueError): parse_duration(s)
    def test_empty(self): self.bad("")
    def test_blank(self): self.bad("   ")
    def test_unknown_unit(self): self.bad("5w")
    def test_missing_number(self): self.bad("h")
    def test_decimal(self): self.bad("1.5h")
    def test_repeat(self): self.bad("1h1h")
    def test_order(self): self.bad("30m1h")
    def test_negative(self): self.bad("-5m")
    def test_garbage(self): self.bad("1h abc")
