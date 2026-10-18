import unittest
from unittest import mock

from src import calculator, sheets


class CalculateTests(unittest.TestCase):
    def test_returns_result_and_records_it(self):
        recorded = []
        with mock.patch.object(
            sheets, "record_result", side_effect=lambda *row: recorded.append(row)
        ):
            self.assertEqual(calculator.calculate("add", 2, 3), 5)
            self.assertEqual(calculator.calculate("multiply", 4, 5), 20)

        self.assertEqual(recorded, [("add", 2, 3, 5), ("multiply", 4, 5, 20)])

    def test_unsupported_operation_raises(self):
        with self.assertRaises(ValueError):
            calculator.calculate("divide", 1, 2)

    def test_recording_failure_does_not_break_calculation(self):
        with mock.patch.object(sheets, "record_result", side_effect=RuntimeError("boom")):
            self.assertEqual(calculator.calculate("add", 1, 1), 2)


if __name__ == "__main__":
    unittest.main()
