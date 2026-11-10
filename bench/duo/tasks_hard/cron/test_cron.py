import unittest
from datetime import datetime
from cron import next_run


class Basic(unittest.TestCase):
    def test_every_minute(self):
        self.assertEqual(next_run("* * * * *", datetime(2026, 1, 1, 10, 0)), datetime(2026, 1, 1, 10, 1))


if __name__ == "__main__":
    unittest.main()
