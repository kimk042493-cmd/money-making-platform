from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

BUSINESS_STATUSES = {"idea", "active", "paused", "closed"}
LEAD_STATUSES = ("new", "contacted", "proposal", "won", "lost")
TRANSACTION_KINDS = {"income", "expense"}


class UserInputError(ValueError):
    """Raised when an operation contains invalid user input."""


def _required(value: str, label: str, limit: int = 160) -> str:
    value = value.strip()
    if not value:
        raise UserInputError(f"{label} is required.")
    if len(value) > limit:
        raise UserInputError(f"{label} must be {limit} characters or fewer.")
    return value


def _amount_cents(value: str) -> int:
    try:
        amount = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise UserInputError("Enter a valid amount.") from None
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise UserInputError("Amount must be positive and have no more than two decimals.")
    if amount > Decimal("9999999999.99"):
        raise UserInputError("Amount is too large.")
    cents = int(amount * 100)
    return cents


def _valid_date(value: str) -> str:
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except (ValueError, AttributeError):
        raise UserInputError("Enter a valid date.") from None


class Store:
    """SQLite persistence for businesses and their day-to-day operations."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
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
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS businesses (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK (status IN ('idea','active','paused','closed')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY,
                    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    contact TEXT NOT NULL DEFAULT '',
                    value_cents INTEGER NOT NULL CHECK (value_cents > 0),
                    status TEXT NOT NULL CHECK (status IN ('new','contacted','proposal','won','lost')),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY,
                    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0,1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY,
                    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK (kind IN ('income','expense')),
                    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                    description TEXT NOT NULL DEFAULT '',
                    transaction_date TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS leads_business_status ON leads(business_id, status);
                CREATE INDEX IF NOT EXISTS tasks_business_due ON tasks(business_id, completed, due_date);
                CREATE INDEX IF NOT EXISTS transactions_business_date
                    ON transactions(business_id, transaction_date DESC);
                """
            )

    def businesses(self) -> list[dict]:
        with self.connect() as db:
            businesses = [dict(row) for row in db.execute(
                "SELECT * FROM businesses ORDER BY created_at DESC, id DESC"
            )]
            grouped = {
                business["id"]: {"leads": [], "tasks": [], "transactions": []}
                for business in businesses
            }
            for table, order in (
                ("leads", "id DESC"),
                ("tasks", "completed, due_date, id DESC"),
                ("transactions", "transaction_date DESC, id DESC"),
            ):
                for row in db.execute(f"SELECT * FROM {table} ORDER BY {order}"):
                    grouped[row["business_id"]][table].append(dict(row))
            for business in businesses:
                business.update(grouped[business["id"]])
        return businesses

    def totals(self) -> dict[str, int]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT kind, COALESCE(SUM(amount_cents), 0) total FROM transactions GROUP BY kind"
            ).fetchall()
            result = {"income": 0, "expense": 0}
            result.update({row["kind"]: row["total"] for row in rows})
            result["pipeline"] = db.execute(
                "SELECT COALESCE(SUM(value_cents), 0) FROM leads WHERE status NOT IN ('won','lost')"
            ).fetchone()[0]
            result["open_tasks"] = db.execute(
                "SELECT COUNT(*) FROM tasks WHERE completed=0"
            ).fetchone()[0]
            result["net"] = result["income"] - result["expense"]
        return result

    def create_business(self, name: str, description: str, status: str) -> int:
        name = _required(name, "Business name")
        description = description.strip()
        if len(description) > 500:
            raise UserInputError("Description must be 500 characters or fewer.")
        if status not in BUSINESS_STATUSES:
            raise UserInputError("Choose a valid business status.")
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO businesses(name, description, status) VALUES (?, ?, ?)",
                (name, description, status),
            )
            return cursor.lastrowid

    def update_business(self, business_id: int, name: str, description: str, status: str) -> None:
        name = _required(name, "Business name")
        if len(description.strip()) > 500:
            raise UserInputError("Description must be 500 characters or fewer.")
        if status not in BUSINESS_STATUSES:
            raise UserInputError("Choose a valid business status.")
        self._update("UPDATE businesses SET name=?, description=?, status=? WHERE id=?",
                     (name, description.strip(), status, business_id), "Business not found.")

    def delete_business(self, business_id: int) -> None:
        self._delete("DELETE FROM businesses WHERE id=?", (business_id,), "Business not found.")

    def add_lead(self, business_id: int, name: str, contact: str, value: str) -> int:
        name = _required(name, "Lead name")
        contact = contact.strip()
        if len(contact) > 160:
            raise UserInputError("Contact must be 160 characters or fewer.")
        cents = _amount_cents(value)
        with self.connect() as db:
            self._require_business(db, business_id)
            cursor = db.execute(
                "INSERT INTO leads(business_id,name,contact,value_cents,status) VALUES(?,?,?,?, 'new')",
                (business_id, name, contact, cents),
            )
            return cursor.lastrowid

    def update_lead_status(self, lead_id: int, status: str) -> None:
        if status not in LEAD_STATUSES:
            raise UserInputError("Choose a valid lead status.")
        self._update("UPDATE leads SET status=? WHERE id=?", (status, lead_id), "Lead not found.")

    def delete_lead(self, lead_id: int) -> None:
        self._delete("DELETE FROM leads WHERE id=?", (lead_id,), "Lead not found.")

    def add_task(self, business_id: int, title: str, due_date: str) -> int:
        title = _required(title, "Task title")
        due_date = _valid_date(due_date)
        with self.connect() as db:
            self._require_business(db, business_id)
            cursor = db.execute(
                "INSERT INTO tasks(business_id,title,due_date) VALUES(?,?,?)",
                (business_id, title, due_date),
            )
            return cursor.lastrowid

    def toggle_task(self, task_id: int) -> None:
        self._update("UPDATE tasks SET completed=1-completed WHERE id=?", (task_id,), "Task not found.")

    def delete_task(self, task_id: int) -> None:
        self._delete("DELETE FROM tasks WHERE id=?", (task_id,), "Task not found.")

    def add_transaction(
        self, business_id: int, kind: str, amount: str, description: str, transaction_date: str
    ) -> int:
        if kind not in TRANSACTION_KINDS:
            raise UserInputError("Choose income or expense.")
        cents = _amount_cents(amount)
        description = description.strip()
        if len(description) > 240:
            raise UserInputError("Description must be 240 characters or fewer.")
        transaction_date = _valid_date(transaction_date)
        with self.connect() as db:
            self._require_business(db, business_id)
            cursor = db.execute(
                """INSERT INTO transactions(business_id,kind,amount_cents,description,transaction_date)
                   VALUES(?,?,?,?,?)""",
                (business_id, kind, cents, description, transaction_date),
            )
            return cursor.lastrowid

    def delete_transaction(self, transaction_id: int) -> None:
        self._delete("DELETE FROM transactions WHERE id=?", (transaction_id,), "Transaction not found.")

    def _update(self, query: str, parameters: tuple, missing: str) -> None:
        with self.connect() as db:
            cursor = db.execute(query, parameters)
            if cursor.rowcount != 1:
                raise UserInputError(missing)

    @staticmethod
    def _require_business(db: sqlite3.Connection, business_id: int) -> None:
        if db.execute("SELECT 1 FROM businesses WHERE id=?", (business_id,)).fetchone() is None:
            raise UserInputError("Business not found.")

    def _delete(self, query: str, parameters: tuple, missing: str) -> None:
        self._update(query, parameters, missing)
