import tempfile
import unittest

from src import app


class TestApp(unittest.TestCase):
    def test_add_positive(self):
        self.assertEqual(app.add(2, 3), 5)

    def test_add_negative(self):
        self.assertEqual(app.add(-1, -1), -2)

    def test_multiply_positive(self):
        self.assertEqual(app.multiply(3, 4), 12)

    def test_multiply_by_zero(self):
        self.assertEqual(app.multiply(5, 0), 0)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = app.Store(f"{self.temp_dir.name}/test.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_businesses_and_financial_totals(self):
        business_id = self.store.create_business("Studio", "Design services", "active")
        self.store.add_transaction(business_id, "income", "1250.99", "Project", "2026-10-24")
        self.store.add_transaction(business_id, "expense", "50.25", "Hosting", "2026-10-24")

        self.assertEqual(
            self.store.totals(),
            {"income": 125099, "expense": 5025, "net": 120074, "pipeline": 0, "open_tasks": 0},
        )
        business = self.store.businesses()[0]
        self.assertEqual(business["name"], "Studio")
        self.assertEqual(len(business["transactions"]), 2)

    def test_updates_and_deletes_business_with_cascade(self):
        business_id = self.store.create_business("Old name", "", "idea")
        self.store.add_transaction(business_id, "income", "10.00", "", "2026-10-24")
        self.store.add_lead(business_id, "Customer", "", "25.00")
        self.store.add_task(business_id, "Follow up", "2026-10-25")
        self.store.update_business(business_id, "New name", "Updated", "active")
        self.assertEqual(self.store.businesses()[0]["name"], "New name")

        self.store.delete_business(business_id)
        self.assertEqual(self.store.businesses(), [])
        self.assertEqual(self.store.totals()["income"], 0)
        self.assertEqual(self.store.totals()["pipeline"], 0)
        self.assertEqual(self.store.totals()["open_tasks"], 0)

    def test_rejects_invalid_amounts_and_statuses(self):
        business_id = self.store.create_business("Studio", "", "active")
        with self.assertRaises(app.UserInputError):
            self.store.add_transaction(business_id, "income", "1.001", "", "2026-10-24")
        with self.assertRaises(app.UserInputError):
            self.store.add_transaction(business_id, "income", "-1", "", "2026-10-24")
        with self.assertRaises(app.UserInputError):
            self.store.create_business("Invalid", "", "unknown")

    def test_sales_pipeline_and_task_workflow(self):
        business_id = self.store.create_business("Studio", "", "active")
        self.store.add_lead(business_id, "Acme project", "buyer@example.test", "200.00")
        self.store.add_task(business_id, "Send proposal", "2026-10-25")

        self.assertEqual(self.store.totals()["pipeline"], 20000)
        self.assertEqual(self.store.totals()["open_tasks"], 1)
        self.assertEqual(self.store.businesses()[0]["leads"][0]["status"], "new")

        lead_id = self.store.businesses()[0]["leads"][0]["id"]
        task_id = self.store.businesses()[0]["tasks"][0]["id"]
        self.store.update_lead_status(lead_id, "proposal")
        self.store.toggle_task(task_id)
        self.assertEqual(self.store.businesses()[0]["leads"][0]["status"], "proposal")
        self.assertEqual(self.store.totals()["open_tasks"], 0)

        self.store.update_lead_status(lead_id, "won")
        self.assertEqual(self.store.totals()["pipeline"], 0)
        self.store.delete_lead(lead_id)
        self.store.delete_task(task_id)
        self.assertEqual(self.store.businesses()[0]["leads"], [])
        self.assertEqual(self.store.businesses()[0]["tasks"], [])

    def test_rejects_invalid_leads_and_tasks(self):
        business_id = self.store.create_business("Studio", "", "active")
        with self.assertRaises(app.UserInputError):
            self.store.add_lead(business_id, "Prospect", "", "0")
        with self.assertRaises(app.UserInputError):
            self.store.add_task(business_id, "Follow up", "not-a-date")
        with self.assertRaises(app.UserInputError):
            self.store.update_lead_status(999, "invalid")

    def test_escapes_business_content(self):
        self.store.create_business("<script>alert(1)</script>", "", "idea")
        business_id = self.store.businesses()[0]["id"]
        self.store.add_lead(business_id, "<img src=x>", "", "10.00")
        self.store.add_task(business_id, "<svg onload=alert(1)>", "2026-10-25")
        page = app.render_page(self.store, "token")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn("&lt;img src=x&gt;", page)
        self.assertIn("&lt;svg onload=alert(1)&gt;", page)
        self.assertNotIn("<script>alert(1)</script>", page)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = app.Store(f"{self.temp_dir.name}/dashboard.sqlite3")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dashboard_renders_business_forms_and_cash_flow(self):
        business_id = self.store.create_business("Test business", "Test description", "active")
        self.store.add_transaction(business_id, "income", "100.50", "First sale", "2026-10-24")
        self.store.add_lead(business_id, "Potential customer", "", "250.00")
        self.store.add_task(business_id, "Contact customer", "2026-10-25")
        page = app.render_page(self.store, "test-csrf-token")

        self.assertIn("Business portfolio", page)
        self.assertIn("Test business", page)
        self.assertIn("First sale", page)
        self.assertIn("$100.50", page)
        self.assertIn("Potential customer", page)
        self.assertIn("Contact customer", page)
        self.assertIn("$250.00", page)
        self.assertIn("Open pipeline", page)
        self.assertIn("Open tasks", page)
        self.assertIn('action="/businesses"', page)
        self.assertIn(f'action="/businesses/{business_id}/transactions"', page)
        self.assertIn(f'action="/businesses/{business_id}/leads"', page)
        self.assertIn(f'action="/businesses/{business_id}/tasks"', page)
        self.assertIn('name="csrf" value="test-csrf-token"', page)


class RouteWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = app.Store(f"{self.temp_dir.name}/routes.sqlite3")

        class ResponseHandler(app.BusinessHandler):
            def send_response(handler_self, status, message=None):
                handler_self.status = status

            def send_header(handler_self, *_):
                pass

            def end_headers(handler_self):
                pass

            def send_error(handler_self, status, message=None):
                handler_self.status = status

        self.handler = object.__new__(ResponseHandler)
        self.handler.store = self.store

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sales_task_and_finance_routes(self):
        self.handler.handle_form(
            "/businesses",
            {"name": "Services", "description": "", "status": "active"},
        )
        business_id = self.store.businesses()[0]["id"]
        self.handler.handle_form(
            f"/businesses/{business_id}/leads",
            {"name": "New client", "contact": "", "value": "300.00"},
        )
        lead_id = self.store.businesses()[0]["leads"][0]["id"]
        self.handler.handle_form(f"/leads/{lead_id}/status", {"status": "proposal"})
        self.handler.handle_form(
            f"/businesses/{business_id}/tasks",
            {"title": "Send proposal", "due_date": "2026-10-25"},
        )
        task_id = self.store.businesses()[0]["tasks"][0]["id"]
        self.handler.handle_form(f"/tasks/{task_id}/toggle", {})
        self.handler.handle_form(
            f"/businesses/{business_id}/transactions",
            {
                "kind": "income",
                "amount": "300.00",
                "description": "Client deposit",
                "date": "2026-10-24",
            },
        )

        self.assertEqual(self.handler.status, app.HTTPStatus.SEE_OTHER)
        self.assertEqual(self.store.businesses()[0]["leads"][0]["status"], "proposal")
        self.assertEqual(self.store.totals()["open_tasks"], 0)
        self.assertEqual(self.store.totals()["income"], 30000)
        self.assertEqual(self.store.totals()["pipeline"], 30000)


if __name__ == "__main__":
    unittest.main()
