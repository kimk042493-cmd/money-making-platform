# Northstar Business Operations Workspace

A local-first operations workspace for running a portfolio of small businesses. Track prospects through a simple sales pipeline, turn follow-ups into dated tasks, and record income and expenses to review cash flow. It runs on Python's standard library and stores data in a local SQLite database.

## Operating workflows

- **Organize the portfolio:** create businesses and keep their operating status current.
- **Work the sales pipeline:** record prospects and estimated deal values; move each opportunity through new, contacted, proposal, won, or lost. Open pipeline excludes closed won/lost opportunities.
- **Keep execution moving:** write the next action as a dated task and mark it complete when done.
- **Review cash flow:** record dated income and expenses and see portfolio totals alongside the open pipeline and open task count.
- **Keep the records local:** business, lead, task, and transaction records persist in `data/businesses.sqlite3`.

## Run on Windows

1. Double-click `scripts\setup-dev.cmd` once. It creates the isolated `.venv` and runs the tests.
2. Double-click `start-app.cmd` in the project folder to start the local app and open it in your browser. You can also double-click `scripts\run-app.cmd`.
3. Use `http://127.0.0.1:8000` if the browser does not open automatically.
4. Close the command window to stop the app.

To run the tests later, double-click `scripts\test.cmd`.

The app binds to `127.0.0.1` and is intended for use on the same computer only. It does not have accounts, multi-user access, cloud sync, customer communications, payment processing, invoicing, tax/accounting integrations, automatic backups, or production deployment configuration. The open pipeline is a planning estimate, not guaranteed revenue. Cash-flow totals are not accounting, tax, or financial advice. This is an operations MVP, not a production-ready finance or customer-record system; do not rely on it as the only record system for a real business.

## Isolated development environment

The project uses a repository-local Python virtual environment, separate from the system Python installation. It requires Python 3.10 or newer and installs no third-party packages. `.venv` and the local SQLite database are excluded from version control.

## Project tests

The test suite covers business, lead, task, and transaction workflows; financial and pipeline totals; validation; database cascades; HTML escaping; and dashboard rendering.
