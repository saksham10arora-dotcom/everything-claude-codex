import unittest
from prices import total


class Total(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(total([10, 20]), 30)


if __name__ == "__main__":
    unittest.main()
