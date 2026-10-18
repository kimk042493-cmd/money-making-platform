"""Perform arithmetic and keep a permanent record of every result."""
from __future__ import annotations

import logging

from src import app, sheets

log = logging.getLogger(__name__)

_OPERATIONS = {"add": app.add, "multiply": app.multiply}


def calculate(operation: str, a, b):
    """Run ``operation`` on ``a`` and ``b``, record the result, return it."""
    try:
        func = _OPERATIONS[operation]
    except KeyError:
        raise ValueError(f"unsupported operation: {operation!r}") from None

    result = func(a, b)
    try:
        sheets.record_result(operation, a, b, result)
    except Exception:  # a failed export must never break a calculation
        log.exception("failed to record calculation in Google Sheets")
    return result
