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


if __name__ == "__main__":
    unittest.main()
