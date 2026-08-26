"""Unit tests for bank statement balance chain helpers."""
from decimal import Decimal

from src.infrastructure.reconciliation.statement_chain import (
    extract_statement_balances,
    prior_month,
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
