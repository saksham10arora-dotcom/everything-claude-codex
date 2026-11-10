import unittest
from lru import LRUCache


class Hidden(unittest.TestCase):
    def test_get_refreshes(self):
        c = LRUCache(2); c.put("a", 1); c.put("b", 2); c.get("a"); c.put("c", 3)
        self.assertEqual(c.keys(), ["a", "c"])
    def test_update_refreshes(self):
        c = LRUCache(2); c.put("a", 1); c.put("b", 2); c.put("a", 9); c.put("c", 3)
        self.assertEqual((c.keys(), c.get("a")), (["a", "c"], 9))
    def test_zero_capacity(self):
        c = LRUCache(0); c.put("a", 1)
        self.assertEqual((len(c), c.get("a")), (0, None))
    def test_negative_capacity(self):
        with self.assertRaises(ValueError): LRUCache(-1)
    def test_contains_no_refresh(self):
        c = LRUCache(2); c.put("a", 1); c.put("b", 2); self.assertTrue("a" in c); c.put("c", 3)
        self.assertFalse("a" in c)
    def test_default(self):
        self.assertEqual(LRUCache(1).get("x", 7), 7)
    def test_order(self):
        c = LRUCache(3); c.put(1, 1); c.put(2, 2); c.put(3, 3); c.get(1)
        self.assertEqual(c.keys(), [2, 3, 1])
    def test_len(self):
        c = LRUCache(2); c.put(1, 1); c.put(1, 2)
        self.assertEqual(len(c), 1)
