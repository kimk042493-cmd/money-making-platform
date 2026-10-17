import unittest

from performance.cache import memoize


class MemoizeTests(unittest.TestCase):
    def test_memoize_returns_cached_value_for_repeated_calls(self):
        calls = 0

        @memoize(max_size=8)
        def compute_total(value: int, scale: int = 1) -> int:
            nonlocal calls
            calls += 1
            return value * scale

        self.assertEqual(compute_total(3, scale=2), 6)
        self.assertEqual(compute_total(3, scale=2), 6)
        self.assertEqual(calls, 1)

    def test_memoize_clears_when_cache_is_full(self):
        calls = 0

        @memoize(max_size=2)
        def compute(value: int) -> int:
            nonlocal calls
            calls += 1
            return value * 10

        self.assertEqual(compute(1), 10)
        self.assertEqual(compute(2), 20)
        self.assertEqual(compute(3), 30)
        self.assertEqual(compute(3), 30)
        self.assertGreater(calls, 2)

    def test_memoize_evicts_least_recently_used_entry(self):
        calls = 0

        @memoize(max_size=2)
        def compute(value: int) -> int:
            nonlocal calls
            calls += 1
            return value * 10

        compute(1)
        compute(2)
        compute(1)
        compute(3)
        compute(1)
        self.assertEqual(calls, 3)
        compute(2)
        self.assertEqual(calls, 4)

    def test_memoize_requires_positive_max_size(self):
        with self.assertRaises(ValueError):
            memoize(max_size=0)


if __name__ == "__main__":
    unittest.main()
