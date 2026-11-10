import unittest
from semver import satisfies

CASES = [
 ("1.2.3", "^1.2.3", True), ("1.9.9", "^1.2.3", True), ("2.0.0", "^1.2.3", False), ("1.2.2", "^1.2.3", False),
 ("0.2.5", "^0.2.3", True), ("0.3.0", "^0.2.3", False), ("0.0.3", "^0.0.3", True), ("0.0.4", "^0.0.3", False),
 ("1.2.9", "~1.2.3", True), ("1.3.0", "~1.2.3", False), ("1.2.0", "~1.2", True), ("1.9.0", "~1", True), ("2.0.0", "~1", False),
 ("1.2.7", "1.2.x", True), ("1.3.0", "1.2.x", False), ("1.2.7", "1.2", True), ("1.7.0", "1.x", True), ("2.0.0", "1", False),
 ("3.4.5", "*", True), ("3.4.5", "", True),
 ("1.2.3-beta.4", "^1.2.3-beta.2", True), ("1.2.4-beta.1", "^1.2.3-beta.2", False), ("1.2.3-beta.1", "^1.2.3-beta.2", False),
 ("1.2.3", "^1.2.3-beta.2", True), ("1.0.0-rc.1", "*", False), ("1.0.0-rc.1", ">=0.9.0", False),
 ("1.0.0-alpha.10", "^1.0.0-alpha.9", True), ("1.0.0-alpha.beta", "^1.0.0-alpha.1", True), ("1.0.0-alpha", "^1.0.0-alpha.1", False),
 ("1.0.0+build.5", "=1.0.0", True), ("1.0.0", "1.0.0+other", True),
 ("2.5.0", "^1.0.0 || ^2.0.0", True), ("3.0.0", "^1.0.0 || ^2.0.0", False),
 ("1.5.0", ">=1.2.0 <1.5.0", False), ("1.4.9", ">=1.2.0 <1.5.0", True), ("1.2.0", ">1.2.0", False), ("1.2.0", "<=1.2.0", True),
]


class Hidden(unittest.TestCase):
    pass


def _case(v, r, want):
    return lambda self: self.assertEqual(satisfies(v, r), want, f"{v} in {r!r}")


def _bad(v):
    def t(self):
        with self.assertRaises(ValueError):
            satisfies(v, "*")
    return t


for i, (v, r, want) in enumerate(CASES):
    setattr(Hidden, f"test_case_{i:02d}", _case(v, r, want))
for i, v in enumerate(("1.2", "01.2.3", "1.2.3-", "a.b.c")):
    setattr(Hidden, f"test_invalid_{i}", _bad(v))
