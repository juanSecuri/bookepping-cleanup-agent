"""Sprint 15 — QuickBooks-style cumulative month columns helpers."""
from __future__ import annotations

from src.use_cases.emit_period_reports import MONTH_KEYS, cumulative_by_month


def test_cumulative_by_month_running_sum() -> None:
    activity = {mk: 0.0 for mk in MONTH_KEYS}
    activity["01"] = 10.0
    activity["03"] = 5.0
    activity["12"] = 2.0
    cum = cumulative_by_month(activity)
    assert cum["01"] == 10.0
    assert cum["02"] == 10.0
    assert cum["03"] == 15.0
    assert cum["11"] == 15.0
    assert cum["12"] == 17.0


def test_cumulative_empty() -> None:
    cum = cumulative_by_month({})
    assert all(cum[mk] == 0.0 for mk in MONTH_KEYS)
