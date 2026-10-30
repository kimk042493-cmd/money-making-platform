import math
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

    def test_memoize_uses_default_argument_values_for_cache_keys(self):
        calls = 0

        @memoize(max_size=8)
        def compute(value: int, scale: int = 2) -> int:
            nonlocal calls
            calls += 1
            return value * scale

        self.assertEqual(compute(3), 6)
        self.assertEqual(compute(3, scale=2), 6)
        self.assertEqual(calls, 1)

    def test_memoize_distinguishes_argument_types_and_container_types(self):
        calls = 0

        @memoize(max_size=8)
        def describe(value):
            nonlocal calls
            calls += 1
            return type(value), value

        self.assertEqual(describe(1), (int, 1))
        self.assertEqual(describe(True), (bool, True))
        self.assertEqual(describe([1]), (list, [1]))
        self.assertEqual(describe((1,)), (tuple, (1,)))
        self.assertEqual(calls, 4)

    def test_memoize_distinguishes_signed_zero(self):
        calls = 0

        @memoize(max_size=8)
        def signs(value):
            nonlocal calls
            calls += 1
            if isinstance(value, complex):
                return (
                    math.copysign(1, value.real),
                    math.copysign(1, value.imag),
                )
            return math.copysign(1, value)

        self.assertEqual(signs(0.0), 1.0)
        self.assertEqual(signs(-0.0), -1.0)
        self.assertEqual(signs(complex(0.0, 0.0)), (1.0, 1.0))
        self.assertEqual(signs(complex(-0.0, 0.0)), (-1.0, 1.0))
        self.assertEqual(signs(complex(0.0, -0.0)), (1.0, -1.0))
        self.assertEqual(calls, 5)

    def test_memoize_handles_mixed_dictionary_keys(self):
        calls = 0

        @memoize(max_size=8)
        def total(values):
            nonlocal calls
            calls += 1
            return sum(values.values())

        values = {1: 2, "two": 3}
        self.assertEqual(total(values), 5)
        self.assertEqual(total(values.copy()), 5)
        self.assertEqual(calls, 1)

    def test_memoize_preserves_dictionary_insertion_order(self):
        calls = 0

        @memoize(max_size=8)
        def keys_in_order(values):
            nonlocal calls
            calls += 1
            return tuple(values)

        self.assertEqual(keys_in_order({"first": 1, "second": 2}), ("first", "second"))
        self.assertEqual(keys_in_order({"second": 2, "first": 1}), ("second", "first"))
        self.assertEqual(calls, 2)

    def test_memoize_preserves_keyword_argument_order(self):
        calls = 0

        @memoize(max_size=8)
        def keys_in_order(**values):
            nonlocal calls
            calls += 1
            return tuple(values)

        self.assertEqual(keys_in_order(first=1, second=2), ("first", "second"))
        self.assertEqual(keys_in_order(second=2, first=1), ("second", "first"))
        self.assertEqual(calls, 2)

    def test_memoize_does_not_cache_recursive_containers(self):
        calls = 0

        @memoize(max_size=8)
        def compute(value):
            nonlocal calls
            calls += 1
            return calls

        recursive = []
        recursive.append(recursive)
        self.assertEqual(compute(recursive), 1)
        self.assertEqual(compute(recursive), 2)
        self.assertEqual(calls, 2)

    def test_memoize_does_not_cache_unsupported_unhashable_values(self):
        class MutableValue:
            __hash__ = None

        calls = 0

        @memoize(max_size=8)
        def compute(value):
            nonlocal calls
            calls += 1
            return calls

        value = MutableValue()
        self.assertEqual(compute(value), 1)
        self.assertEqual(compute(value), 2)
        self.assertEqual(calls, 2)

    def test_memoize_counts_failed_calls_as_misses(self):
        @memoize(max_size=8)
        def fail(value):
            raise ValueError(value)

        with self.assertRaisesRegex(ValueError, "bad"):
            fail("bad")

        self.assertEqual(fail.cache_info().misses, 1)

    def test_memoize_requires_positive_max_size(self):
        with self.assertRaises(ValueError):
            memoize(max_size=0)
        with self.assertRaises(ValueError):
            memoize(max_size=1.5)
        with self.assertRaises(ValueError):
            memoize(max_size=True)


if __name__ == "__main__":
    unittest.main()
