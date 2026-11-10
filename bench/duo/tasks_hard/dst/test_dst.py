import unittest
from datetime import datetime, timezone
from dst import next_daily


class Basic(unittest.TestCase):
    def test_utc(self):
        self.assertEqual(next_daily(9, 0, "UTC", datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)),
                         datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
