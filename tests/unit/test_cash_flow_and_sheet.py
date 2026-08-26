"""Tests for cash_flow_type inference and spreadsheet header helpers."""
from src.infrastructure.classification.cash_flow import infer_cash_flow_type
from src.use_cases.ingest_spreadsheet import _find_col, _norm_header, _parse_amount, _parse_date


def test_infer_cash_flow_type() -> None:
    assert infer_cash_flow_type(account_code="3030") == "financing"
    assert infer_cash_flow_type(account_code="2010", account_type="liability") == "financing"
    assert infer_cash_flow_type(account_code="1510", account_type="asset") == "investing"
    assert infer_cash_flow_type(account_code="1010", account_type="asset") == "operating"
    assert infer_cash_flow_type(account_code="6020", account_type="expense") == "operating"


def test_spreadsheet_headers_and_parse() -> None:
    headers = [_norm_header(h) for h in ["Date", "Description", "Debit", "Credit"]]
    assert _find_col(headers, ("date", "fecha")) == 0
    assert _find_col(headers, ("description", "desc")) == 1
    assert _parse_amount("1,234.50") == __import__("decimal").Decimal("1234.50")
    assert _parse_date("2026-08-15").isoformat() == "2026-08-15"
