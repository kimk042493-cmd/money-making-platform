import unittest
from unittest import mock

from src import sheets


class FakeWorksheet:
    def __init__(self):
        self.rows = []

    def get_all_values(self):
        return []

    def append_row(self, row):
        self.rows.append(row)


class SheetsTests(unittest.TestCase):
    def test_not_configured_without_credentials(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(sheets.is_configured())

    def test_configured_with_sheet_id_and_json_key(self):
        env = {
            "GOOGLE_SHEET_ID": "abc123",
            "GOOGLE_SERVICE_ACCOUNT_JSON": "{}",
        }
        with mock.patch.dict("os.environ", env, clear=True):
            self.assertTrue(sheets.is_configured())

    def test_record_is_noop_when_not_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(sheets.record_result("add", 2, 3, 5))

    def test_record_appends_timestamp_operation_and_result(self):
        fake = FakeWorksheet()
        with mock.patch.object(sheets, "_get_worksheet", return_value=fake):
            self.assertTrue(sheets.record_result("multiply", 4, 5, 20))

        self.assertEqual(len(fake.rows), 1)
        timestamp, operation, a, b, result = fake.rows[0]
        self.assertEqual(operation, "multiply")
        self.assertEqual((a, b, result), (4, 5, 20))
        self.assertTrue(timestamp)


if __name__ == "__main__":
    unittest.main()
