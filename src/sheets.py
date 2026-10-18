"""Append every calculation result to a Google Sheet.

The target spreadsheet and the service-account credentials are supplied
through the environment:

* ``GOOGLE_SHEET_ID`` - the id of the spreadsheet that collects the results.
* ``GOOGLE_SERVICE_ACCOUNT_JSON`` - the service-account key, as raw JSON.
  ``GOOGLE_SERVICE_ACCOUNT_FILE`` pointing at a key file is also accepted.

The service account's ``client_email`` must be shared on the spreadsheet with
edit access. When no credentials are configured the recorder is a no-op, so
the rest of the app keeps working without them.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADER = ["Timestamp (UTC)", "Operation", "A", "B", "Result"]

_lock = threading.Lock()
_worksheet = None
_initialized = False


def is_configured() -> bool:
    """True when a spreadsheet id and service-account credentials are present."""
    return bool(os.environ.get("GOOGLE_SHEET_ID")) and bool(
        os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        or os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
    )


def _load_client():
    import gspread
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw:
        info = json.loads(raw)
        credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        credentials = Credentials.from_service_account_file(
            os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"], scopes=SCOPES
        )
    return gspread.authorize(credentials)


def _get_worksheet():
    """Return the target worksheet, connecting once and caching the handle."""
    global _worksheet, _initialized
    with _lock:
        if _initialized:
            return _worksheet
        _initialized = True
        if not is_configured():
            return None
        sheet = _load_client().open_by_key(os.environ["GOOGLE_SHEET_ID"]).sheet1
        if not sheet.get_all_values():
            sheet.append_row(HEADER)
        _worksheet = sheet
        return _worksheet


def record_result(operation, a, b, result) -> bool:
    """Append one calculation to the sheet. Returns True when it was recorded."""
    worksheet = _get_worksheet()
    if worksheet is None:
        return False
    worksheet.append_row(
        [
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            operation,
            a,
            b,
            result,
        ]
    )
    return True
