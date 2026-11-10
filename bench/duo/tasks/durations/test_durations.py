import unittest
from durations import parse_duration


class Parse(unittest.TestCase):
    def test_spaced(self):
        self.assertEqual(parse_duration("1h 30m"), 5400)


if __name__ == "__main__":
    unittest.main()
