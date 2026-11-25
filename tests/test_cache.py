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

    def test_memoize_uses_same_entry_when_keyword_order_differs(self):
        calls = 0

        @memoize()
        def compute_total(*, subtotal: int, tax: int) -> int:
            nonlocal calls
            calls += 1
            return subtotal + tax

        self.assertEqual(compute_total(subtotal=10, tax=2), 12)
        self.assertEqual(compute_total(tax=2, subtotal=10), 12)
        self.assertEqual(calls, 1)

    def test_memoize_caches_none_results(self):
        calls = 0

        @memoize()
        def compute(value: int) -> None:
            nonlocal calls
            calls += 1
            return None

        self.assertIsNone(compute(1))
        self.assertIsNone(compute(1))
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

    def test_memoize_clear_forces_recomputation(self):
        calls = 0

        @memoize()
        def compute(value: int) -> int:
            nonlocal calls
            calls += 1
            return value * 10

        self.assertEqual(compute(2), 20)
        compute.clear()
        self.assertEqual(compute(2), 20)
        self.assertEqual(calls, 2)

    def test_memoize_does_not_cache_exceptions(self):
        calls = 0

        @memoize()
        def compute(value: int) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary failure")
            return value * 10

        with self.assertRaisesRegex(RuntimeError, "temporary failure"):
            compute(2)

        self.assertEqual(compute(2), 20)
        self.assertEqual(calls, 2)

    def test_memoize_requires_positive_max_size(self):
        for max_size in (0, -1):
            with self.subTest(max_size=max_size):
                with self.assertRaises(ValueError):
                    memoize(max_size=max_size)


if __name__ == "__main__":
    unittest.main()
