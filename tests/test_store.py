import tempfile
import unittest
from pathlib import Path

from src.store import Store, UserInputError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp_dir.name) / "test.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_business_workflows_persist_and_aggregate(self):
        business_id = self.store.create_business("Studio", "Creative services", "active")
        lead_id = self.store.add_lead(business_id, "New client", "client@example.test", "1250.50")
        task_id = self.store.add_task(business_id, "Send proposal", "2026-10-30")
        self.store.add_transaction(business_id, "income", "300.25", "Deposit", "2026-10-29")
        self.store.add_transaction(business_id, "expense", "50.10", "Hosting", "2026-10-29")

        business = self.store.businesses()[0]
        self.assertEqual(business["name"], "Studio")
        self.assertEqual(business["leads"][0]["id"], lead_id)
        self.assertEqual(business["tasks"][0]["id"], task_id)
        self.assertEqual(self.store.totals(), {
            "income": 30025, "expense": 5010, "pipeline": 125050, "open_tasks": 1, "net": 25015,
        })
        reopened = Store(self.store.db_path)
        self.assertEqual(reopened.businesses()[0]["name"], "Studio")
        self.assertEqual(reopened.totals()["net"], 25015)

        self.store.update_lead_status(lead_id, "won")
        self.store.toggle_task(task_id)
        self.assertEqual(self.store.totals()["pipeline"], 0)
        self.assertEqual(self.store.totals()["open_tasks"], 0)

    def test_updates_and_deletes_business_with_cascade(self):
        business_id = self.store.create_business("Old name", "", "idea")
        self.store.add_transaction(business_id, "income", "10.00", "", "2026-10-29")
        self.store.add_lead(business_id, "Prospect", "", "25.00")
        self.store.add_task(business_id, "Follow up", "2026-10-30")
        self.store.update_business(business_id, "New name", "Updated", "active")
        self.assertEqual(self.store.businesses()[0]["name"], "New name")

        self.store.delete_business(business_id)
        self.assertEqual(self.store.businesses(), [])
        self.assertEqual(self.store.totals(), {
            "income": 0, "expense": 0, "pipeline": 0, "open_tasks": 0, "net": 0,
        })

    def test_rejects_invalid_input(self):
        business_id = self.store.create_business("Studio", "", "active")
        invalid = (
            lambda: self.store.create_business("", "", "idea"),
            lambda: self.store.create_business("Bad status", "", "unknown"),
            lambda: self.store.add_transaction(business_id, "income", "1.001", "", "2026-10-29"),
            lambda: self.store.add_transaction(business_id, "income", "-1", "", "2026-10-29"),
            lambda: self.store.add_transaction(business_id, "income", "1e999999999", "", "2026-10-29"),
            lambda: self.store.add_lead(business_id, "Prospect", "", "0"),
            lambda: self.store.add_task(business_id, "Follow up", "not-a-date"),
            lambda: self.store.update_lead_status(999, "unknown"),
        )
        for operation in invalid:
            with self.subTest(operation=operation):
                with self.assertRaises(UserInputError):
                    operation()

    def test_business_delete_cascades_and_values_are_stored_as_cents(self):
        business_id = self.store.create_business("Cafe", "", "active")
        self.store.add_transaction(business_id, "income", "1.10", "Sale", "2026-10-29")
        self.assertEqual(self.store.businesses()[0]["transactions"][0]["amount_cents"], 110)
        self.store.delete_business(business_id)
        self.assertEqual(self.store.totals()["income"], 0)


if __name__ == "__main__":
    unittest.main()
