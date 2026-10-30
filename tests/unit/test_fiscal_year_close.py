"""Period window resolution (as-of date drives the Balance Sheet year)."""

from src.use_cases.emit_period_reports import resolve_period


def _win(**kw):
    base = dict(
        period=None, date_from=None, date_to=None, fiscal_year=None, month=None, ceiling=None
    )
    base.update(kw)
    return resolve_period(**base)


def test_annual_window() -> None:
    w = _win(fiscal_year="2025")
    assert (w["date_from"], w["date_to"], w["granularity"]) == (
        "2025-01-01",
        "2025-12-31",
        "annual",
    )


def test_monthly_window_ends_on_last_day() -> None:
    w = _win(fiscal_year="2024", month=2)
    assert (w["date_from"], w["date_to"], w["month"]) == ("2024-02-01", "2024-02-29", 2)


def test_ceiling_caps_future_years() -> None:
    w = _win(fiscal_year="2026", month=5, ceiling=2025)
    assert w["year"] == "2025" and w["granularity"] == "annual"


def test_range_year_from_date_to() -> None:
    assert _win(date_to="2024-12-31")["year"] == "2024"
