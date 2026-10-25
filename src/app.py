from __future__ import annotations

import html
import os
import re
import secrets
import sqlite3
import webbrowser
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qs, urlparse


def add(a, b):
    """Return the sum of a and b."""
    return a + b


def multiply(a, b):
    """Return the product of a and b."""
    return a * b


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "businesses.sqlite3"
MAX_REQUEST_SIZE = 64 * 1024
STATUSES = {"idea", "active", "paused", "closed"}
TRANSACTION_TYPES = {"income", "expense"}
LEAD_STATUSES = {"new", "contacted", "proposal", "won", "lost"}


class UserInputError(ValueError):
    """Raised when a submitted business or transaction is invalid."""


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS businesses (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK (status IN ('idea', 'active', 'paused', 'closed')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY,
                    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK (kind IN ('income', 'expense')),
                    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                    description TEXT NOT NULL DEFAULT '',
                    transaction_date TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS transactions_business_date
                    ON transactions (business_id, transaction_date DESC, id DESC);
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY,
                    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    contact TEXT NOT NULL DEFAULT '',
                    value_cents INTEGER NOT NULL CHECK (value_cents > 0),
                    status TEXT NOT NULL CHECK (status IN ('new', 'contacted', 'proposal', 'won', 'lost')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS leads_business_status
                    ON leads (business_id, status, id DESC);
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS tasks_business_due
                    ON tasks (business_id, completed, due_date);
                """
            )

    def businesses(self) -> list[dict]:
        with self.connect() as connection:
            businesses = connection.execute(
                "SELECT * FROM businesses ORDER BY created_at DESC, id DESC"
            ).fetchall()
            transactions = connection.execute(
                "SELECT * FROM transactions ORDER BY transaction_date DESC, id DESC"
            ).fetchall()
            leads = connection.execute(
                "SELECT * FROM leads ORDER BY id DESC"
            ).fetchall()
            tasks = connection.execute(
                "SELECT * FROM tasks ORDER BY completed, due_date, id DESC"
            ).fetchall()
        by_business: dict[int, dict[str, list[dict]]] = {
            business["id"]: {"transactions": [], "leads": [], "tasks": []}
            for business in businesses
        }
        for transaction in transactions:
            by_business[transaction["business_id"]]["transactions"].append(dict(transaction))
        for lead in leads:
            by_business[lead["business_id"]]["leads"].append(dict(lead))
        for task in tasks:
            by_business[task["business_id"]]["tasks"].append(dict(task))
        return [
            {**dict(business), **by_business[business["id"]]}
            for business in businesses
        ]

    def totals(self) -> dict[str, int]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT kind, COALESCE(SUM(amount_cents), 0) AS total
                FROM transactions GROUP BY kind
                """
            ).fetchall()
        result = {"income": 0, "expense": 0}
        for row in rows:
            result[row["kind"]] = row["total"]
        result["net"] = result["income"] - result["expense"]
        with self.connect() as connection:
            result["pipeline"] = connection.execute(
                "SELECT COALESCE(SUM(value_cents), 0) FROM leads WHERE status NOT IN ('won', 'lost')"
            ).fetchone()[0]
            result["open_tasks"] = connection.execute(
                "SELECT COUNT(*) FROM tasks WHERE completed = 0"
            ).fetchone()[0]
        return result

    @staticmethod
    def validate_date(value: str, label: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise UserInputError(f"Enter a valid {label}.") from None
        if parsed.isoformat() != value:
            raise UserInputError(f"Enter a valid {label}.")
        return value

    @staticmethod
    def positive_cents(amount: str, label: str) -> int:
        try:
            decimal_amount = Decimal(amount)
            if not decimal_amount.is_finite() or decimal_amount <= 0:
                raise InvalidOperation
            cents_value = decimal_amount * 100
            if cents_value != cents_value.to_integral_value() or cents_value > 999_999_999_999:
                raise InvalidOperation
            return int(cents_value)
        except (InvalidOperation, ValueError):
            raise UserInputError(f"Enter a {label} greater than zero with no more than two decimal places.") from None

    def create_business(self, name: str, description: str, status: str) -> int:
        name = name.strip()
        description = description.strip()
        if not name or len(name) > 100:
            raise UserInputError("Business name is required and must be 100 characters or fewer.")
        if len(description) > 500:
            raise UserInputError("Description must be 500 characters or fewer.")
        if status not in STATUSES:
            raise UserInputError("Choose a valid business status.")
        with self.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO businesses (name, description, status) VALUES (?, ?, ?)",
                (name, description, status),
            )
            return int(cursor.lastrowid)

    def update_business(self, business_id: int, name: str, description: str, status: str) -> None:
        name = name.strip()
        description = description.strip()
        if not name or len(name) > 100:
            raise UserInputError("Business name is required and must be 100 characters or fewer.")
        if len(description) > 500:
            raise UserInputError("Description must be 500 characters or fewer.")
        if status not in STATUSES:
            raise UserInputError("Choose a valid business status.")
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE businesses SET name = ?, description = ?, status = ? WHERE id = ?",
                (name, description, status, business_id),
            )
            if cursor.rowcount == 0:
                raise UserInputError("Business not found.")

    def delete_business(self, business_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM businesses WHERE id = ?", (business_id,))
            if cursor.rowcount == 0:
                raise UserInputError("Business not found.")

    def add_transaction(
        self,
        business_id: int,
        kind: str,
        amount: str,
        description: str,
        transaction_date: str,
    ) -> None:
        if kind not in TRANSACTION_TYPES:
            raise UserInputError("Choose income or expense.")
        amount_cents = self.positive_cents(amount, "amount")
        self.validate_date(transaction_date, "transaction date")
        description = description.strip()
        if len(description) > 200:
            raise UserInputError("Transaction description must be 200 characters or fewer.")
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM businesses WHERE id = ?", (business_id,)
            ).fetchone()
            if exists is None:
                raise UserInputError("Business not found.")
            connection.execute(
                """
                INSERT INTO transactions
                    (business_id, kind, amount_cents, description, transaction_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (business_id, kind, amount_cents, description, transaction_date),
            )

    def add_lead(self, business_id: int, name: str, contact: str, value: str) -> None:
        name = name.strip()
        contact = contact.strip()
        if not name or len(name) > 100:
            raise UserInputError("Lead or opportunity name is required (100 characters max).")
        if len(contact) > 160:
            raise UserInputError("Contact details must be 160 characters or fewer.")
        value_cents = self.positive_cents(value, "estimated value")
        with self.connect() as connection:
            if connection.execute("SELECT 1 FROM businesses WHERE id = ?", (business_id,)).fetchone() is None:
                raise UserInputError("Business not found.")
            connection.execute(
                "INSERT INTO leads (business_id, name, contact, value_cents, status) VALUES (?, ?, ?, ?, 'new')",
                (business_id, name, contact, value_cents),
            )

    def update_lead_status(self, lead_id: int, status: str) -> None:
        if status not in LEAD_STATUSES:
            raise UserInputError("Choose a valid sales stage.")
        with self.connect() as connection:
            cursor = connection.execute("UPDATE leads SET status = ? WHERE id = ?", (status, lead_id))
            if cursor.rowcount == 0:
                raise UserInputError("Opportunity not found.")

    def delete_lead(self, lead_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
            if cursor.rowcount == 0:
                raise UserInputError("Opportunity not found.")

    def add_task(self, business_id: int, title: str, due_date: str) -> None:
        title = title.strip()
        if not title or len(title) > 160:
            raise UserInputError("Task is required and must be 160 characters or fewer.")
        self.validate_date(due_date, "due date")
        with self.connect() as connection:
            if connection.execute("SELECT 1 FROM businesses WHERE id = ?", (business_id,)).fetchone() is None:
                raise UserInputError("Business not found.")
            connection.execute(
                "INSERT INTO tasks (business_id, title, due_date) VALUES (?, ?, ?)",
                (business_id, title, due_date),
            )

    def toggle_task(self, task_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE tasks SET completed = CASE completed WHEN 0 THEN 1 ELSE 0 END WHERE id = ?",
                (task_id,),
            )
            if cursor.rowcount == 0:
                raise UserInputError("Task not found.")

    def delete_task(self, task_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if cursor.rowcount == 0:
                raise UserInputError("Task not found.")

    def delete_transaction(self, transaction_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            if cursor.rowcount == 0:
                raise UserInputError("Transaction not found.")


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def money(cents: int) -> str:
    return f"${Decimal(cents) / 100:,.2f}"


def status_options(selected: str) -> str:
    return "".join(
        f'<option value="{status}"{" selected" if status == selected else ""}>'
        f"{status.title()}</option>"
        for status in ("idea", "active", "paused", "closed")
    )


def lead_status_options(selected: str) -> str:
    return "".join(
        f'<option value="{status}"{" selected" if status == selected else ""}>{status.title()}</option>'
        for status in ("new", "contacted", "proposal", "won", "lost")
    )


def render_page(store: Store, csrf_token: str, error: str = "") -> str:
    businesses = store.businesses()
    totals = store.totals()
    cards = []
    for business in businesses:
        transactions = []
        for transaction in business["transactions"]:
            label = "Income" if transaction["kind"] == "income" else "Expense"
            amount_class = transaction["kind"]
            transactions.append(
                f"""
                <li class="transaction">
                  <div><strong>{escape(transaction["description"] or label)}</strong>
                    <span>{escape(transaction["transaction_date"])} · {label}</span></div>
                  <strong class="{amount_class}">{money(transaction["amount_cents"])}</strong>
                  <form method="post" action="/transactions/{transaction["id"]}/delete">
                    <input type="hidden" name="csrf" value="{csrf_token}">
                    <button class="icon-button" aria-label="Delete transaction" title="Delete transaction">×</button>
                  </form>
                </li>
                """
            )
        transaction_list = "".join(transactions) or '<li class="empty-row">No transactions yet.</li>'
        leads = []
        for lead in business["leads"]:
            leads.append(
                f"""
                <li class="work-row">
                  <div><strong>{escape(lead["name"])}</strong>
                    <span>{escape(lead["contact"]) or "No contact details"}</span></div>
                  <strong>{money(lead["value_cents"])}</strong>
                  <form method="post" action="/leads/{lead["id"]}/status" class="inline-form">
                    <input type="hidden" name="csrf" value="{csrf_token}">
                    <select name="status" aria-label="Sales stage">{lead_status_options(lead["status"])}</select>
                    <button class="icon-button" aria-label="Save sales stage" title="Save sales stage">↵</button>
                  </form>
                  <form method="post" action="/leads/{lead["id"]}/delete">
                    <input type="hidden" name="csrf" value="{csrf_token}">
                    <button class="icon-button" aria-label="Delete opportunity" title="Delete opportunity">×</button>
                  </form>
                </li>
                """
            )
        lead_list = "".join(leads) or '<li class="empty-row">No opportunities yet. Add a prospect to start your sales pipeline.</li>'
        tasks = []
        for task in business["tasks"]:
            state = "completed" if task["completed"] else ""
            tasks.append(
                f"""
                <li class="work-row {state}">
                  <form method="post" action="/tasks/{task["id"]}/toggle">
                    <input type="hidden" name="csrf" value="{csrf_token}">
                    <button class="check-button" aria-label="Mark task {'open' if task["completed"] else 'complete'}">
                      {"✓" if task["completed"] else "○"}
                    </button>
                  </form>
                  <div><strong>{escape(task["title"])}</strong>
                    <span>Due {escape(task["due_date"])}</span></div>
                  <form method="post" action="/tasks/{task["id"]}/delete">
                    <input type="hidden" name="csrf" value="{csrf_token}">
                    <button class="icon-button" aria-label="Delete task" title="Delete task">×</button>
                  </form>
                </li>
                """
            )
        task_list = "".join(tasks) or '<li class="empty-row">No tasks yet. Add the next action to keep momentum.</li>'
        cards.append(
            f"""
            <article class="business-card">
              <div class="business-heading">
                <div><span class="status status-{escape(business["status"])}">{escape(business["status"])}</span>
                  <h3>{escape(business["name"])}</h3></div>
                <details class="edit-menu">
                  <summary>Edit</summary>
                  <form method="post" action="/businesses/{business["id"]}/update" class="stack-form">
                    <label>Name<input name="name" maxlength="100" required value="{escape(business["name"])}"></label>
                    <label>Description<textarea name="description" maxlength="500">{escape(business["description"])}</textarea></label>
                    <label>Status<select name="status">{status_options(business["status"])}</select></label>
                    <input type="hidden" name="csrf" value="{csrf_token}">
                    <button class="button secondary" type="submit">Save changes</button>
                  </form>
                </details>
              </div>
              <p class="description">{escape(business["description"]) or "No description added."}</p>
              <details class="transaction-entry">
                <summary>＋ Add income or expense</summary>
                <form method="post" action="/businesses/{business["id"]}/transactions" class="transaction-form">
                  <label>Type<select name="kind"><option value="income">Income</option>
                    <option value="expense">Expense</option></select></label>
                  <label>Amount<input name="amount" type="number" min="0.01" step="0.01" placeholder="0.00" required></label>
                  <label>Date<input name="date" type="date" value="{date.today().isoformat()}" required></label>
                  <label class="wide">Description<input name="description" maxlength="200" placeholder="What was this for?"></label>
                  <input type="hidden" name="csrf" value="{csrf_token}">
                  <button class="button" type="submit">Add entry</button>
                </form>
              </details>
              <ul class="transactions">{transaction_list}</ul>
              <details class="transaction-entry">
                <summary>＋ Add a sales opportunity</summary>
                <form method="post" action="/businesses/{business["id"]}/leads" class="transaction-form">
                  <label>Prospect or opportunity<input name="name" maxlength="100" placeholder="Customer or deal" required></label>
                  <label>Estimated value<input name="value" type="number" min="0.01" step="0.01" placeholder="0.00" required></label>
                  <label class="wide">Contact details<input name="contact" maxlength="160" placeholder="Email or phone (optional)"></label>
                  <input type="hidden" name="csrf" value="{csrf_token}">
                  <button class="button" type="submit">Add to pipeline</button>
                </form>
              </details>
              <ul class="transactions">{lead_list}</ul>
              <details class="transaction-entry">
                <summary>＋ Add an action item</summary>
                <form method="post" action="/businesses/{business["id"]}/tasks" class="transaction-form">
                  <label class="wide">Next action<input name="title" maxlength="160" placeholder="e.g. Send proposal to prospect" required></label>
                  <label>Due date<input name="due_date" type="date" value="{date.today().isoformat()}" required></label>
                  <input type="hidden" name="csrf" value="{csrf_token}">
                  <button class="button" type="submit">Add task</button>
                </form>
              </details>
              <ul class="transactions">{task_list}</ul>
              <form method="post" action="/businesses/{business["id"]}/delete" class="delete-form"
                    onsubmit="return confirm('Delete this business and all its transactions?')">
                <input type="hidden" name="csrf" value="{csrf_token}">
                <button class="text-button" type="submit">Delete business</button>
              </form>
            </article>
            """
        )
    business_content = "".join(cards) or """
      <div class="empty-state">
        <div class="empty-icon">＋</div><h3>Your portfolio starts here</h3>
        <p>Add a business to start tracking its income, expenses, and operating status.</p>
      </div>
    """
    error_banner = f'<div class="error" role="alert">{escape(error)}</div>' if error else ""
    net_class = "positive" if totals["net"] >= 0 else "negative"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f5f6f4">
  <title>Northstar — Business portfolio</title>
  <style>
    :root {{ color-scheme: light; --ink:#1d2b25; --muted:#68756e; --line:#e3e8e4; --green:#176b4b; --pale:#eaf4ee; --bg:#f5f7f5; }}
    * {{ box-sizing:border-box }} body {{ margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif }}
    header {{ background:#fff;border-bottom:1px solid var(--line) }} .topbar {{ max-width:1120px;margin:auto;padding:18px 24px;display:flex;align-items:center;gap:12px }}
    .brand-mark {{ width:34px;height:34px;border-radius:11px;background:var(--green);color:#fff;display:grid;place-items:center;font-weight:800 }}
    .brand {{ font-weight:750;letter-spacing:-.03em;font-size:18px }} .brand small {{ display:block;color:var(--muted);font-size:11px;font-weight:500;letter-spacing:.04em }}
    main {{ max-width:1120px;margin:38px auto;padding:0 24px 60px }} .intro {{ display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:26px }}
    .eyebrow {{ color:var(--green);font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.12em }} h1 {{ margin:5px 0;font-size:clamp(28px,4vw,38px);line-height:1.15;letter-spacing:-.045em }}
    .intro p,.description {{ color:var(--muted);margin:6px 0 0 }}     .summary {{ display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:30px }}
    .metric,.business-card,.panel {{ background:#fff;border:1px solid var(--line);border-radius:15px }} .metric {{ padding:19px 21px }}
    .metric span {{ color:var(--muted);font-size:13px }} .metric strong {{ display:block;font-size:25px;letter-spacing:-.03em;margin-top:6px }}
    .positive,.income {{ color:var(--green) }} .negative,.expense {{ color:#b04d3e }} .section-heading {{ display:flex;justify-content:space-between;align-items:center;margin-bottom:14px }}
    h2 {{ font-size:19px;letter-spacing:-.025em;margin:0 }} .count {{ color:var(--muted);font-size:13px }}
    .business-grid {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:16px }}
    .business-card {{ padding:20px }} .business-heading {{ display:flex;justify-content:space-between;align-items:start;gap:12px }}
    h3 {{ margin:5px 0 0;font-size:20px;letter-spacing:-.03em }} .status {{ display:inline-block;padding:3px 9px;border-radius:99px;background:#f0f2f0;color:#59655e;font-size:11px;font-weight:700;text-transform:capitalize }}
    .status-active {{ color:#176b4b;background:#eaf4ee }} .status-idea {{ color:#785313;background:#fbf2dc }} .status-paused {{ color:#5b6181;background:#eff0f8 }} .status-closed {{ color:#8a514b;background:#f8ecea }}
    details summary {{ cursor:pointer;color:var(--green);font-weight:650;font-size:13px }} .edit-menu {{ position:relative }} .edit-menu[open] {{ z-index:2 }}
    .stack-form {{ position:absolute;right:0;top:25px;width:min(310px,80vw);padding:16px;background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:0 12px 35px #20352a22;display:grid;gap:11px }}
    label {{ display:grid;gap:5px;color:#536159;font-size:12px;font-weight:650 }} input,select,textarea {{ width:100%;border:1px solid #dce3de;border-radius:8px;padding:9px 10px;background:white;color:var(--ink);font:inherit;font-size:13px;min-width:0 }}
    textarea {{ min-height:66px;resize:vertical }} input:focus,select:focus,textarea:focus {{ outline:2px solid #9bc7ae;outline-offset:1px }}
    .button {{ border:0;border-radius:8px;background:var(--green);color:#fff;padding:10px 15px;font:inherit;font-size:13px;font-weight:700;cursor:pointer }}
    .button:hover {{ background:#10543a }} .secondary {{ background:#edf4ef;color:var(--green) }} .secondary:hover {{ background:#dfeee4 }}
    .description {{ min-height:24px;font-size:13px }} .transaction-entry {{ margin-top:18px;padding:13px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line) }}
    .transaction-form {{ display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px }} .transaction-form .wide {{ grid-column:1/-1 }} .transaction-form button {{ grid-column:1/-1;justify-self:start }}
    .transactions {{ list-style:none;padding:0;margin:5px 0 0 }} .transaction {{ display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid #f0f2f0 }}
    .work-row {{ display:grid;grid-template-columns:1fr auto auto auto;align-items:center;gap:9px;padding:10px 0;border-bottom:1px solid #f0f2f0 }}
    .work-row strong {{ font-size:13px }} .work-row span {{ display:block;color:var(--muted);font-size:11px }} .work-row.completed > div {{ opacity:.55;text-decoration:line-through }}
    .inline-form {{ display:flex;align-items:center;gap:4px }} .inline-form select {{ width:auto;padding:6px;font-size:11px }}
    .check-button {{ border:0;background:none;color:var(--green);font-size:20px;cursor:pointer }}
    .transaction strong {{ font-size:13px }} .transaction span {{ display:block;color:var(--muted);font-size:11px }} .icon-button {{ border:0;background:none;color:#87928b;font-size:20px;cursor:pointer }}
    .empty-row {{ color:var(--muted);font-size:13px;padding:12px 0 }} .delete-form {{ text-align:right;margin-top:9px }} .text-button {{ border:0;background:transparent;color:#9a6259;font-size:12px;cursor:pointer }}
    .empty-state {{ text-align:center;background:#fff;border:1px dashed #cdd8d0;border-radius:15px;padding:46px 20px }} .empty-icon {{ margin:auto;width:42px;height:42px;border-radius:14px;background:var(--pale);color:var(--green);display:grid;place-items:center;font-size:24px }}
    .empty-state h3 {{ margin-top:12px }} .empty-state p {{ max-width:430px;margin:7px auto 0;color:var(--muted);font-size:13px }}
    .panel {{ padding:20px;margin-top:26px }} .new-business {{ display:grid;grid-template-columns:1fr 1fr 1fr auto;align-items:end;gap:12px;margin-top:14px }}
    .error {{ border:1px solid #f0c5bd;background:#fff1ee;color:#843b30;padding:12px 15px;border-radius:10px;margin-bottom:18px }}
    footer {{ color:var(--muted);font-size:12px;margin-top:28px }}
    @media(max-width:900px) {{ .summary {{ grid-template-columns:repeat(3,1fr) }} }}
    @media(max-width:680px) {{ main {{ margin-top:27px;padding:0 16px 40px }} .topbar {{ padding:14px 16px }} .intro {{ align-items:start;flex-direction:column }} .summary {{ grid-template-columns:repeat(2,1fr);gap:8px }} .metric {{ padding:14px 12px }} .metric strong {{ font-size:19px }} .new-business {{ grid-template-columns:1fr 1fr }} .new-business label:first-child,.new-business label:nth-child(2) {{ grid-column:1/-1 }} .new-business button {{ grid-column:1/-1 }} }}
  </style>
</head>
<body>
<header><div class="topbar"><div class="brand-mark">N</div><div class="brand">northstar<small>BUSINESS WORKSPACE</small></div></div></header>
<main>
  {error_banner}
  <section class="intro"><div><div class="eyebrow">Your command center</div><h1>Business portfolio</h1>
  <p>Keep your ventures, operations, and cash flow in one clear view.</p></div></section>
  <section class="summary" aria-label="Portfolio financial summary">
    <div class="metric"><span>Total income</span><strong class="positive">{money(totals["income"])}</strong></div>
    <div class="metric"><span>Total expenses</span><strong class="negative">{money(totals["expense"])}</strong></div>
    <div class="metric"><span>Net cash flow</span><strong class="{net_class}">{money(totals["net"])}</strong></div>
    <div class="metric"><span>Open pipeline</span><strong>{money(totals["pipeline"])}</strong></div>
    <div class="metric"><span>Open tasks</span><strong>{totals["open_tasks"]}</strong></div>
  </section>
  <section><div class="section-heading"><h2>Your businesses</h2><span class="count">{len(businesses)} business{"es" if len(businesses) != 1 else ""}</span></div>
    <div class="business-grid">{business_content}</div>
  </section>
  <section class="panel"><h2>Add a business</h2><form method="post" action="/businesses" class="new-business">
    <label>Business name<input name="name" maxlength="100" placeholder="e.g. Harbor Creative Studio" required></label>
    <label>Description<input name="description" maxlength="500" placeholder="What does this business do?"></label>
    <label>Status<select name="status">{status_options("idea")}</select></label>
    <input type="hidden" name="csrf" value="{csrf_token}"><button class="button" type="submit">＋ Create business</button>
  </form></section>
  <footer>Private local workspace · Your records are stored on this device.</footer>
</main>
</body></html>"""


class BusinessHandler(BaseHTTPRequestHandler):
    store: Store
    server_version = "Northstar/1.0"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def send_html(self, body: str, status: int = HTTPStatus.OK, csrf_token: str | None = None) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        if csrf_token:
            self.send_header(
                "Set-Cookie",
                f"northstar_csrf={csrf_token}; Path=/; HttpOnly; SameSite=Strict",
            )
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if urlparse(self.path).path != "/":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookie["northstar_csrf"].value if "northstar_csrf" in cookie else secrets.token_urlsafe(32)
        self.send_html(render_page(self.store, token), csrf_token=token)

    def read_form(self) -> dict[str, str]:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise UserInputError("Invalid request.") from None
        if content_length < 1 or content_length > MAX_REQUEST_SIZE:
            raise UserInputError("Request is empty or too large.")
        content_type = self.headers.get_content_type()
        if content_type != "application/x-www-form-urlencoded":
            raise UserInputError("Unsupported form submission.")
        form = parse_qs(self.rfile.read(content_length).decode("utf-8"), keep_blank_values=True)
        return {key: values[-1] for key, values in form.items()}

    def do_POST(self) -> None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        cookie_token = cookie["northstar_csrf"].value if "northstar_csrf" in cookie else ""
        try:
            form = self.read_form()
            if not cookie_token or not secrets.compare_digest(form.get("csrf", ""), cookie_token):
                self.send_error(HTTPStatus.FORBIDDEN, "Form expired. Reload the page and try again.")
                return
            self.handle_form(urlparse(self.path).path, form)
        except UserInputError as error:
            token = cookie_token or secrets.token_urlsafe(32)
            self.send_html(render_page(self.store, token, str(error)), HTTPStatus.BAD_REQUEST, token)
        except UnicodeDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid form encoding.")

    def handle_form(self, path: str, form: dict[str, str]) -> None:
        store = self.store
        if path == "/businesses":
            store.create_business(form.get("name", ""), form.get("description", ""), form.get("status", ""))
        elif match := re.fullmatch(r"/businesses/(\d+)/update", path):
            store.update_business(
                int(match.group(1)),
                form.get("name", ""),
                form.get("description", ""),
                form.get("status", ""),
            )
        elif match := re.fullmatch(r"/businesses/(\d+)/delete", path):
            store.delete_business(int(match.group(1)))
        elif match := re.fullmatch(r"/businesses/(\d+)/transactions", path):
            store.add_transaction(
                int(match.group(1)),
                form.get("kind", ""),
                form.get("amount", ""),
                form.get("description", ""),
                form.get("date", ""),
            )
        elif match := re.fullmatch(r"/businesses/(\d+)/leads", path):
            store.add_lead(
                int(match.group(1)),
                form.get("name", ""),
                form.get("contact", ""),
                form.get("value", ""),
            )
        elif match := re.fullmatch(r"/leads/(\d+)/status", path):
            store.update_lead_status(int(match.group(1)), form.get("status", ""))
        elif match := re.fullmatch(r"/leads/(\d+)/delete", path):
            store.delete_lead(int(match.group(1)))
        elif match := re.fullmatch(r"/businesses/(\d+)/tasks", path):
            store.add_task(
                int(match.group(1)),
                form.get("title", ""),
                form.get("due_date", ""),
            )
        elif match := re.fullmatch(r"/tasks/(\d+)/toggle", path):
            store.toggle_task(int(match.group(1)))
        elif match := re.fullmatch(r"/tasks/(\d+)/delete", path):
            store.delete_task(int(match.group(1)))
        elif match := re.fullmatch(r"/transactions/(\d+)/delete", path):
            store.delete_transaction(int(match.group(1)))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()


def run(host: str = "127.0.0.1", port: int = 8000, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    handler = type("ConfiguredBusinessHandler", (BusinessHandler,), {"store": Store(db_path)})
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_port}"
    print(f"Northstar is ready at {url}")
    if not webbrowser.open(url):
        print(f"Open {url} in your browser.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Northstar.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run(port=int(os.environ.get("PORT", "8000")))
