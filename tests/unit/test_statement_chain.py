"""Unit tests for bank statement balance chain helpers."""
from decimal import Decimal

from src.infrastructure.reconciliation.statement_chain import (
    detect_statement_month,
    extract_statement_balances,
    needs_statement_month_detection,
    prior_month,
    resolve_statement_month,
)


def test_prior_month_rolls_year() -> None:
    assert prior_month("2026-01") == "2025-12"
    assert prior_month("2026-08") == "2026-07"
    assert prior_month("bad") is None


def test_extract_opening_closing_balances() -> None:
    text = """
    ACCOUNT SUMMARY
    Beginning Balance $10,250.00
    Deposits 1,200.00
    Ending Balance $9,800.50
    """
    opening, closing = extract_statement_balances(text)
    assert opening == Decimal("10250.00")
    assert closing == Decimal("9800.50")


def test_detect_statement_month_named_period() -> None:
    text = """
    Wells Fargo Business Checking
    Statement Period: January 1, 2026 - January 31, 2026
    Beginning Balance $1,000.00
    """
    assert detect_statement_month(text) == "2026-01"


def test_detect_statement_month_numeric_period() -> None:
    text = "Statement Period: 02/01/2025 - 02/28/2025\nEnding Balance $50.00"
    assert detect_statement_month(text) == "2025-02"


def test_detect_statement_month_period_ending() -> None:
    text = "Period ending March 31, 2024\nAccount Summary"
    assert detect_statement_month(text) == "2024-03"


def test_detect_statement_month_iso_near_keyword() -> None:
    text = "Statement Period 2026-06-01 through 2026-06-30"
    assert detect_statement_month(text) == "2026-06"


def test_resolve_statement_month_detects_placeholder() -> None:
    text = "Statement Period: July 1, 2025 - July 31, 2025"
    assert resolve_statement_month("2026-01", text) == "2025-07"
    assert resolve_statement_month(None, text) == "2025-07"
    assert resolve_statement_month("2025-07", text) == "2025-07"


def test_needs_statement_month_detection() -> None:
    assert needs_statement_month_detection(None) is True
    assert needs_statement_month_detection("") is True
    assert needs_statement_month_detection("2026-01") is True
    assert needs_statement_month_detection("2024-11") is False
