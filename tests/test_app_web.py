import http.client
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

from src.app import BusinessHandler, render_page
from src.store import Store


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp_dir.name) / "web.sqlite3")

        class Handler(BusinessHandler):
            pass

        Handler.store = self.store
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.connection = http.client.HTTPConnection(*self.server.server_address)

    def tearDown(self):
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_dashboard_sets_security_headers_and_escapes_user_content(self):
        self.store.create_business('<script>alert("x")</script>', "", "active")
        self.connection.request("GET", "/")
        response = self.connection.getresponse()
        page = response.read().decode()

        self.assertEqual(response.status, 200)
        self.assertIn("HttpOnly", response.getheader("Set-Cookie"))
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", page)
        self.assertNotIn('<script>alert("x")</script>', page)
        self.assertIn("Business portfolio", page)

    def test_post_requires_csrf_token_and_completes_business_workflow(self):
        self.connection.request("GET", "/")
        response = self.connection.getresponse()
        page = response.read().decode()
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]
        token = re.search(r'name="csrf" value="([^"]+)"', page).group(1)

        self.connection.request(
            "POST", "/businesses",
            body=urlencode({"name": "Northstar Studio", "description": "Design", "status": "active"}),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(self.connection.getresponse().status, 403)

        self.connection.request(
            "POST", "/businesses",
            body=urlencode({
                "csrf": token, "name": "Northstar Studio",
                "description": "Design", "status": "active",
            }),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie},
        )
        response = self.connection.getresponse()
        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), "/")
        response.read()

        business_id = self.store.businesses()[0]["id"]
        for path, values in (
            (f"/businesses/{business_id}/leads", {"name": "Acme", "contact": "", "value": "250.00"}),
            (f"/businesses/{business_id}/tasks", {"title": "Send proposal", "due_date": "2026-10-30"}),
            (f"/businesses/{business_id}/transactions", {
                "kind": "income", "amount": "100.50", "description": "Deposit", "date": "2026-10-29",
            }),
        ):
            self.connection.request(
                "POST", path,
                body=urlencode({"csrf": token, **values}),
                headers={"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie},
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 303)
            response.read()

        page = render_page(self.store, token)
        self.assertIn("Acme", page)
        self.assertIn("Send proposal", page)
        self.assertIn("$100.50", page)
        self.assertIn("$250.00", page)

        business = self.store.businesses()[0]
        actions = (
            (f"/leads/{business['leads'][0]['id']}/status", {"status": "won"}),
            (f"/tasks/{business['tasks'][0]['id']}/toggle", {}),
            (f"/transactions/{business['transactions'][0]['id']}/delete", {}),
        )
        for path, values in actions:
            self.connection.request(
                "POST", path,
                body=urlencode({"csrf": token, **values}),
                headers={"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie},
            )
            response = self.connection.getresponse()
            self.assertEqual(response.status, 303)
            response.read()
        totals = self.store.totals()
        self.assertEqual(totals["pipeline"], 0)
        self.assertEqual(totals["open_tasks"], 0)
        self.assertEqual(totals["income"], 0)

    def test_form_validation_is_shown_without_saving_invalid_data(self):
        self.connection.request("GET", "/")
        response = self.connection.getresponse()
        page = response.read().decode()
        cookie = response.getheader("Set-Cookie").split(";", 1)[0]
        token = re.search(r'name="csrf" value="([^"]+)"', page).group(1)

        self.connection.request(
            "POST", "/businesses",
            body=urlencode({"csrf": token, "name": "", "description": "", "status": "active"}),
            headers={"Content-Type": "application/x-www-form-urlencoded", "Cookie": cookie},
        )
        response = self.connection.getresponse()
        page = response.read().decode()
        self.assertEqual(response.status, 400)
        self.assertIn("Business name is required.", page)
        self.assertEqual(self.store.businesses(), [])


if __name__ == "__main__":
    unittest.main()
