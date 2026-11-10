import unittest
from prices import total


class Hidden(unittest.TestCase):
    def test_percentage(self): self.assertEqual(total([100, 100], 10), 180.0)
    def test_empty(self): self.assertEqual(total([]), 0.0)
    def test_full_discount(self): self.assertEqual(total([50], 100), 0.0)
    def test_discount_over_100(self):
        with self.assertRaises(ValueError): total([10], 101)
    def test_negative_discount(self):
        with self.assertRaises(ValueError): total([10], -1)
    def test_negative_price(self):
        with self.assertRaises(ValueError): total([10, -5])
    def test_half_up(self): self.assertEqual(total([10.005]), 10.01)
    def test_half_up_after_discount(self): self.assertEqual(total([20.01], 50), 10.01)
    def test_float_drift(self): self.assertEqual(total([0.1, 0.2]), 0.3)
