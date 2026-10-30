# Northstar Business Operations Workspace

Northstar is a local-first workspace for operating a portfolio of small businesses. It provides a dashboard for business status, sales prospects, follow-up tasks, and recorded income and expenses. Records persist in a local SQLite database.

## Run the app

Requires Python 3.10 or newer. No third-party packages are required.

```powershell
python -m src.app
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Press `Ctrl+C` in the terminal to stop the server. On Windows, `start-app.cmd` can be double-clicked to launch the same command.

The database is created at `data/businesses.sqlite3` the first time the app runs. Override its location with `NORTHSTAR_DB_PATH`; set `NORTHSTAR_PORT` to choose another local port.

## Workflows

- **Manage a portfolio:** create a business, update its details and status, and remove businesses you no longer track.
- **Track sales:** add prospects with estimated values, record contact details, and move leads through new, contacted, proposal, won, or lost. The open pipeline excludes won and lost leads.
- **Plan follow-ups:** add dated tasks, mark tasks complete, reopen them, or remove them.
- **Record cash flow:** log dated income and expenses. The dashboard summarizes recorded totals and net cash flow.

## Tests

Run the standard-library test suite with:

```powershell
python -m unittest discover -s tests -v
```

## Important limitations

This is a local operations MVP, not a production-ready accounting or customer-record system. It binds to the local computer only and has no user accounts, cloud sync, automatic backups, payment processing, invoicing, tax/accounting integrations, or production deployment configuration. Keep a separate backup of important business records. Pipeline values are estimates, and cash-flow totals are not accounting, tax, or financial advice.
