import unittest
from semver import satisfies


class Basic(unittest.TestCase):
    def test_caret(self):
        self.assertTrue(satisfies("1.4.0", "^1.2.3"))


if __name__ == "__main__":
    unittest.main()
