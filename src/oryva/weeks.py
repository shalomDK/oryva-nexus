"""ISO-week helpers.  2026W01 starts Monday 2025-12-29 (ISO-8601).  Week index w=1 is 2026W01;
w<=0 are history weeks.  Dates are ISO strings 'YYYY-MM-DD' everywhere in the tables."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np

BASE = date(2025, 12, 29)


def week_start(w: int) -> date:
    return BASE + timedelta(days=7 * (w - 1))


def week_start_s(w: int) -> str:
    return week_start(w).isoformat()


def label(w: int) -> str:
    y, wk, _ = week_start(w).isocalendar()
    return f"{y}W{wk:02d}"


def week_of(d) -> int:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return (d - BASE).days // 7 + 1


def weeks_of(series) -> np.ndarray:
    a = np.asarray(series, dtype="datetime64[D]")
    return ((a - np.datetime64(BASE)).astype(np.int64) // 7 + 1).astype(np.int64)


def add_days(d: str, n: int) -> str:
    return (date.fromisoformat(d) + timedelta(days=int(n))).isoformat()


def iso_date(d) -> str:
    return d if isinstance(d, str) else d.isoformat()
