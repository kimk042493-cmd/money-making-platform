from __future__ import annotations

import html
import os
import secrets
import sqlite3
import webbrowser
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.store import LEAD_STATUSES, Store, UserInputError

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "businesses.sqlite3"
MAX_REQUEST_SIZE = 64 * 1024


def add(a, b):
    """Return the sum of a and b."""
    return a + b


def multiply(a, b):
    """Return the product of a and b."""
    return a * b


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    dollars, remainder = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{remainder:02d}"


def _options(values: tuple[str, ...], selected: str) -> str:
    return "".join(
        f'<option value="{_e(value)}"{" selected" if value == selected else ""}>'
        f'{_e(value.title())}</option>'
        for value in values
    )


def render_page(store: Store, csrf_token: str, message: str = "") -> str:
    totals = store.totals()
    businesses = store.businesses()
    alert = f'<div class="notice" role="alert">{_e(message)}</div>' if message else ""
    cards = []
    for business in businesses:
        business_id = business["id"]
        leads = "".join(
            f"""
            <div class="row item">
              <div><strong>{_e(lead["name"])}</strong><small>{_e(lead["contact"] or "No contact")}
                · {_money(lead["value_cents"])}</small></div>
              <form method="post" action="/leads/{lead["id"]}/status" class="inline">
                <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                <select name="status" aria-label="Status for {_e(lead["name"])}">
                  {_options(tuple(LEAD_STATUSES), lead["status"])}
                </select><button class="button subtle" type="submit">Save</button>
              </form>
              <form method="post" action="/leads/{lead["id"]}/delete" class="inline">
                <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                <button class="button danger" type="submit">Delete</button>
              </form>
            </div>"""
            for lead in business["leads"]
        ) or '<p class="muted">No leads yet.</p>'
        tasks = "".join(
            f"""
            <div class="row item">
              <div class="task-title{" done" if task["completed"] else ""}">
                <strong>{_e(task["title"])}</strong><small>Due {_e(task["due_date"])}</small>
              </div>
              <form method="post" action="/tasks/{task["id"]}/toggle" class="inline">
                <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                <button class="button subtle" type="submit">{"Reopen" if task["completed"] else "Complete"}</button>
              </form>
              <form method="post" action="/tasks/{task["id"]}/delete" class="inline">
                <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                <button class="button danger" type="submit">Delete</button>
              </form>
            </div>"""
            for task in business["tasks"]
        ) or '<p class="muted">No follow-ups scheduled.</p>'
        transactions = "".join(
            f'<div class="row item"><div><strong>{_e(tx["description"] or tx["kind"].title())}'
            f'</strong><small>{_e(tx["transaction_date"])}</small></div>'
            f'<strong class="{"positive" if tx["kind"] == "income" else "negative"}">'
            f'{"+" if tx["kind"] == "income" else "−"}{_money(tx["amount_cents"])}</strong>'
            f'<form method="post" action="/transactions/{tx["id"]}/delete" class="inline">'
            f'<input type="hidden" name="csrf" value="{_e(csrf_token)}">'
            f'<button class="button danger" type="submit" aria-label="Delete transaction">'
            f'Delete</button></form></div>'
            for tx in business["transactions"][:8]
        ) or '<p class="muted">No transactions recorded.</p>'
        cards.append(
            f"""
            <article class="business-card">
              <header class="business-heading">
                <div><span class="eyebrow">{_e(business["status"])}</span>
                  <h2>{_e(business["name"])}</h2>
                  <p>{_e(business["description"] or "Add a short description to keep this business organized.")}</p>
                </div>
                <form method="post" action="/businesses/{business_id}/delete">
                  <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                  <button class="button danger" type="submit">Delete business</button>
                </form>
              </header>
              <details class="edit-business"><summary>Edit business details</summary>
                <form method="post" action="/businesses/{business_id}" class="form-grid">
                  <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                  <label>Name<input name="name" maxlength="160" required value="{_e(business["name"])}"></label>
                  <label>Status<select name="status">{_options(("idea", "active", "paused", "closed"), business["status"])}</select></label>
                  <label class="wide">Description<input name="description" maxlength="500" value="{_e(business["description"])}"></label>
                  <button class="button primary" type="submit">Save changes</button>
                </form>
              </details>
              <div class="columns">
                <section><h3>Sales pipeline</h3>{leads}
                  <form method="post" action="/businesses/{business_id}/leads" class="stack-form">
                    <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                    <label>Prospect<input name="name" maxlength="160" required placeholder="Prospect or opportunity"></label>
                    <label>Contact<input name="contact" maxlength="160" placeholder="Email or phone"></label>
                    <label>Estimated value<input name="value" inputmode="decimal" required placeholder="0.00"></label>
                    <button class="button primary" type="submit">Add lead</button>
                  </form>
                </section>
                <section><h3>Follow-up tasks</h3>{tasks}
                  <form method="post" action="/businesses/{business_id}/tasks" class="stack-form">
                    <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                    <label>Task<input name="title" maxlength="160" required placeholder="Next action"></label>
                    <label>Due date<input name="due_date" type="date" required value="{date.today().isoformat()}"></label>
                    <button class="button primary" type="submit">Add task</button>
                  </form>
                </section>
                <section class="finance"><h3>Cash flow</h3>{transactions}
                  <form method="post" action="/businesses/{business_id}/transactions" class="stack-form">
                    <input type="hidden" name="csrf" value="{_e(csrf_token)}">
                    <label>Type<select name="kind"><option value="income">Income</option><option value="expense">Expense</option></select></label>
                    <label>Amount<input name="amount" inputmode="decimal" required placeholder="0.00"></label>
                    <label>Description<input name="description" maxlength="240" placeholder="What was this for?"></label>
                    <label>Date<input name="date" type="date" required value="{date.today().isoformat()}"></label>
                    <button class="button primary" type="submit">Record transaction</button>
                  </form>
                </section>
              </div>
            </article>"""
        )
    portfolio = "".join(cards) or """
      <div class="empty-state"><div class="empty-icon">✳</div>
        <h2>Your next venture starts here</h2>
        <p>Create a business to start tracking leads, follow-ups, and cash flow in one place.</p>
      </div>"""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>Northstar · Business workspace</title>
<style>
:root{{--ink:#1d2735;--muted:#697586;--line:#e4e9ef;--paper:#fff;--canvas:#f5f7fa;--blue:#245cce;--green:#16734a;--red:#b64040}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--canvas);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
button,input,select{{font:inherit}}.shell{{max-width:1200px;margin:auto;padding:34px 24px 70px}}
.topbar{{display:flex;justify-content:space-between;align-items:center;margin-bottom:32px}}.brand{{font-weight:750;letter-spacing:-.03em;font-size:19px}}
.brand-mark{{display:inline-grid;place-items:center;width:30px;height:30px;border-radius:9px;background:#1d3557;color:#fff;margin-right:9px}}
.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.11em;color:var(--blue);font-weight:750}}
h1{{font-size:clamp(28px,4vw,40px);line-height:1.1;letter-spacing:-.045em;margin:8px 0}}.intro{{color:var(--muted);max-width:600px;margin:0}}
.overview{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:26px 0 34px}}.metric,.panel,.business-card{{background:var(--paper);border:1px solid var(--line);border-radius:14px}}
.metric{{padding:17px 19px}}.metric span{{display:block;color:var(--muted);font-size:13px}}.metric strong{{font-size:25px;letter-spacing:-.03em;display:block;margin-top:3px}}
.create-panel{{padding:20px;margin-bottom:24px}}.create-panel h2{{margin:0 0 14px;font-size:17px}}
.form-grid{{display:grid;grid-template-columns:2fr 1fr 2fr auto;align-items:end;gap:12px}}label{{display:grid;gap:6px;color:#4f5c6e;font-size:12px;font-weight:650}}
input,select{{min-width:0;width:100%;border:1px solid #d5dce5;border-radius:8px;padding:9px 10px;background:#fff;color:var(--ink);font-size:14px}}
input:focus,select:focus,button:focus-visible,summary:focus-visible{{outline:3px solid #91b5fa;outline-offset:2px}}
.button{{border:0;border-radius:8px;padding:9px 12px;font-weight:650;font-size:13px;cursor:pointer;white-space:nowrap}}
.primary{{background:var(--blue);color:#fff}}.subtle{{background:#edf2fa;color:#334e7d}}.danger{{background:#fff0ef;color:var(--red)}}
.notice{{padding:12px 15px;background:#fff5e5;border:1px solid #f1d9a9;border-radius:9px;margin:0 0 17px;color:#754b08}}
.business-list{{display:grid;gap:18px}}.business-card{{padding:21px}}.business-heading{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}}
h2{{letter-spacing:-.025em}}.business-heading h2{{font-size:23px;margin:3px 0}}.business-heading p{{color:var(--muted);margin:0;max-width:600px}}
.columns{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-top:22px}}.columns section{{min-width:0;border-top:1px solid var(--line);padding-top:14px}}
.columns h3{{font-size:14px;margin:0 0 8px}}.row{{display:flex;gap:8px;align-items:center;justify-content:space-between}}.item{{padding:9px 0;border-bottom:1px solid #eff2f5}}
.item strong{{font-size:13px}}.item small{{display:block;color:var(--muted);font-size:11px}}.inline{{display:inline-flex;align-items:center;gap:5px}}.inline select{{width:auto;padding:6px;font-size:12px}}
.inline .button{{padding:7px 8px;font-size:11px}}.positive{{color:var(--green)}}.negative{{color:var(--red)}}.muted{{color:var(--muted);font-size:13px;margin:12px 0}}
.stack-form{{display:grid;gap:9px;margin-top:13px;padding:12px;background:#f8f9fb;border-radius:10px}}.stack-form label{{font-size:11px}}
.stack-form .button{{justify-self:start;margin-top:2px}}.task-title.done strong{{text-decoration:line-through;color:var(--muted)}}
.edit-business{{margin-top:13px;color:var(--muted);font-size:13px}}.edit-business summary{{cursor:pointer;width:max-content}}.edit-business .form-grid{{grid-template-columns:2fr 1fr 2fr auto;margin-top:12px}}
.empty-state{{text-align:center;padding:56px 20px;background:#fff;border:1px dashed #cbd4df;border-radius:14px}}.empty-state h2{{margin:7px 0}}.empty-state p{{color:var(--muted);margin:0}}
.empty-icon{{margin:auto;display:grid;place-items:center;background:#edf3ff;color:var(--blue);height:44px;width:44px;border-radius:14px;font-size:25px}}
footer{{margin-top:25px;color:var(--muted);font-size:11px;text-align:center}}
@media(max-width:850px){{.columns{{grid-template-columns:1fr 1fr}}.finance{{grid-column:span 2}}.form-grid,.edit-business .form-grid{{grid-template-columns:1fr 1fr}}}}
@media(max-width:560px){{.shell{{padding:22px 14px 48px}}.overview{{grid-template-columns:1fr 1fr;gap:9px}}.metric{{padding:13px}}.metric strong{{font-size:21px}}.columns{{grid-template-columns:1fr}}.finance{{grid-column:auto}}.business-card{{padding:15px}}.business-heading{{display:block}}.business-heading>form{{margin-top:10px}}.form-grid,.edit-business .form-grid{{grid-template-columns:1fr}}}}
</style></head>
<body><main class="shell">
  <div class="topbar"><div class="brand"><span class="brand-mark">N</span>Northstar</div><span class="eyebrow">Private workspace</span></div>
  {alert}
  <section><div class="eyebrow">Your operations at a glance</div><h1>Business portfolio</h1>
    <p class="intro">Keep your ventures moving: manage prospects, plan the next action, and review income and expenses.</p>
  </section>
  <section class="overview" aria-label="Portfolio summary">
    <div class="metric"><span>Income recorded</span><strong>{_money(totals["income"])}</strong></div>
    <div class="metric"><span>Expenses recorded</span><strong>{_money(totals["expense"])}</strong></div>
    <div class="metric"><span>Net cash flow</span><strong class="{"positive" if totals["net"] >= 0 else "negative"}">{_money(totals["net"])}</strong></div>
    <div class="metric"><span>Open pipeline · {totals["open_tasks"]} open tasks</span><strong>{_money(totals["pipeline"])}</strong></div>
  </section>
  <section class="panel create-panel"><h2>Add a business</h2>
    <form method="post" action="/businesses" class="form-grid">
      <input type="hidden" name="csrf" value="{_e(csrf_token)}">
      <label>Business name<input name="name" maxlength="160" required placeholder="e.g. Studio North"></label>
      <label>Starting status<select name="status"><option value="idea">Idea</option><option value="active">Active</option><option value="paused">Paused</option><option value="closed">Closed</option></select></label>
      <label>Description<input name="description" maxlength="500" placeholder="What does this business do?"></label>
      <button class="button primary" type="submit">Create business</button>
    </form>
  </section>
  <section class="business-list" aria-label="Businesses">{portfolio}</section>
  <footer>Stored on this computer only. Pipeline is an estimate; cash-flow totals are not accounting or tax advice.</footer>
</main></body></html>"""


class BusinessHandler(BaseHTTPRequestHandler):
    store: Store
    server_version = "Northstar/1.0"

    def do_GET(self) -> None:
        if urlparse(self.path).path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        token = self._csrf_cookie()
        body = render_page(self.store, token).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Set-Cookie", f"northstar_csrf={token}; Path=/; HttpOnly; SameSite=Strict")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_REQUEST_SIZE:
                raise UserInputError("Request is too large.")
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                raise UserInputError("Unsupported form submission.")
            raw = self.rfile.read(length).decode("utf-8")
            form = {key: values[-1] for key, values in parse_qs(raw, keep_blank_values=True).items()}
            cookie = self.headers.get("Cookie", "")
            cookies = {}
            for item in cookie.split(";"):
                name, separator, value = item.strip().partition("=")
                if separator:
                    cookies[name] = value
            token = cookies.get("northstar_csrf", "")
            if not token or not secrets.compare_digest(token, form.get("csrf", "")):
                self.send_error(HTTPStatus.FORBIDDEN, "Refresh the page and try again.")
                return
            self.handle_form(urlparse(self.path).path, form)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        except UserInputError as exc:
            self._show_error(str(exc), HTTPStatus.BAD_REQUEST)
        except (ValueError, UnicodeDecodeError):
            self._show_error("The submitted form could not be read.", HTTPStatus.BAD_REQUEST)
        except sqlite3.Error as exc:
            self.log_error("Database operation failed for %s: %s", self.path, exc)
            self._show_error("The change could not be saved. Check the local database and try again.",
                             HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_form(self, path: str, form: dict[str, str]) -> None:
        if path == "/businesses":
            self.store.create_business(form.get("name", ""), form.get("description", ""),
                                       form.get("status", ""))
            return
        parts = path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "businesses" and parts[1].isdigit():
            business_id = int(parts[1])
            self.store.update_business(business_id, form.get("name", ""), form.get("description", ""),
                                       form.get("status", ""))
            return
        if len(parts) == 3 and parts[0] == "businesses" and parts[1].isdigit():
            business_id = int(parts[1])
            if parts[2] == "delete":
                self.store.delete_business(business_id)
            elif parts[2] == "leads":
                self.store.add_lead(business_id, form.get("name", ""), form.get("contact", ""),
                                    form.get("value", ""))
            elif parts[2] == "tasks":
                self.store.add_task(business_id, form.get("title", ""), form.get("due_date", ""))
            elif parts[2] == "transactions":
                self.store.add_transaction(business_id, form.get("kind", ""), form.get("amount", ""),
                                           form.get("description", ""), form.get("date", ""))
            else:
                raise UserInputError("That action is not available.")
            return
        if len(parts) == 3 and parts[0] in {"leads", "tasks"} and parts[1].isdigit():
            entity_id = int(parts[1])
            if parts[0] == "leads" and parts[2] == "status":
                self.store.update_lead_status(entity_id, form.get("status", ""))
            elif parts[0] == "leads" and parts[2] == "delete":
                self.store.delete_lead(entity_id)
            elif parts[0] == "tasks" and parts[2] == "toggle":
                self.store.toggle_task(entity_id)
            elif parts[0] == "tasks" and parts[2] == "delete":
                self.store.delete_task(entity_id)
            else:
                raise UserInputError("That action is not available.")
            return
        if len(parts) == 3 and parts[0] == "transactions" and parts[1].isdigit() and parts[2] == "delete":
            self.store.delete_transaction(int(parts[1]))
            return
        raise UserInputError("That action is not available.")

    def _csrf_cookie(self) -> str:
        cookie = self.headers.get("Cookie", "")
        for item in cookie.split(";"):
            name, separator, value = item.strip().partition("=")
            if separator and name == "northstar_csrf" and 20 <= len(value) <= 128:
                return value
        return secrets.token_urlsafe(32)

    def _show_error(self, message: str, status: HTTPStatus) -> None:
        body = render_page(self.store, self._csrf_cookie(), message).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def serve(host: str = "127.0.0.1", port: int = 8000, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    store = Store(db_path)

    class Handler(BusinessHandler):
        pass

    Handler.store = store
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    address, actual_port = server.server_address
    url = f"http://{address}:{actual_port}"
    print(f"Northstar is ready at {url} (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Northstar.")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve(
        port=int(os.environ.get("NORTHSTAR_PORT", "8000")),
        db_path=os.environ.get("NORTHSTAR_DB_PATH", DEFAULT_DB_PATH),
    )
