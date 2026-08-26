"""Unit tests for fiscal year close helpers."""
from src.use_cases.emit_period_reports import EmitPeriodReportsUseCase


def test_as_of_year_from_period() -> None:
    assert EmitPeriodReportsUseCase._as_of_year("2026-08", None, None) == "2026"
    assert EmitPeriodReportsUseCase._as_of_year("2025", None, None) == "2025"
    assert EmitPeriodReportsUseCase._as_of_year(None, "2024-12-31", None) == "2024"
