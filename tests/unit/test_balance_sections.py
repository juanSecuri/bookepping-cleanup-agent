"""Unit tests for Balance Sheet CoA zero-merge and subcategory sections (Sprint 14 T2)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.domain.models.enums import DocumentSource, TransactionStatus, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.use_cases.emit_period_reports import (
    EmitPeriodReportsUseCase,
    MONTH_KEYS,
    _acct_bucket,
    build_balance_sections,
    cumulative_by_month,
    merge_coa_zero_balances,
)


def test_cumulative_by_month_running_sum() -> None:
    activity = {"01": 10.0, "02": 5.0, "03": -3.0}
    cum = cumulative_by_month(activity)
    assert cum["01"] == 10.0
    assert cum["02"] == 15.0
    assert cum["03"] == 12.0
    assert cum["04"] == 12.0
    assert list(cum.keys()) == MONTH_KEYS


def test_merge_coa_zero_balances_adds_missing_accounts() -> None:
    asset_map = {"1010": _acct_bucket()}
    asset_map["1010"]["code"] = "1010"
    asset_map["1010"]["name"] = "Cash"
    asset_map["1010"]["amount"] = Decimal("50")
    liability_map: dict = {}
    equity_map: dict = {}
    coa = {
        "1010": {"name": "Cash and Cash Equivalents", "account_type": "asset", "subcategory": "Current Assets"},
        "1020": {"name": "Accounts Receivable", "account_type": "asset", "subcategory": "Current Assets"},
        "1510": {"name": "Equipment", "account_type": "asset", "subcategory": "Fixed Assets"},
        "2010": {"name": "Accounts Payable", "account_type": "liability", "subcategory": "Current Liabilities"},
        "2510": {"name": "Long-Term Debt", "account_type": "liability", "subcategory": "Long-Term Liabilities"},
        "3010": {"name": "Owner's Equity", "account_type": "equity", "subcategory": "Equity"},
        "4010": {"name": "Sales", "account_type": "income", "subcategory": "Operating Revenue"},
    }
    merge_coa_zero_balances(asset_map, liability_map, equity_map, coa)

    assert "1020" in asset_map and float(asset_map["1020"]["amount"]) == 0.0
    assert asset_map["1020"]["subcategory"] == "Current Assets"
    assert "1510" in asset_map and asset_map["1510"]["subcategory"] == "Fixed Assets"
    assert "2010" in liability_map and "2510" in liability_map
    assert "3010" in equity_map
    assert "4010" not in asset_map and "4010" not in liability_map and "4010" not in equity_map
    assert float(asset_map["1010"]["amount"]) == 50.0


def test_build_balance_sections_orders_subcategories() -> None:
    assets = [
        {"code": "1510", "name": "Equipment", "amount": 100.0, "subcategory": "Fixed Assets"},
        {"code": "1010", "name": "Cash", "amount": 50.0, "subcategory": "Current Assets"},
        {"code": "1020", "name": "AR", "amount": 0.0, "subcategory": "Current Assets"},
    ]
    liabilities = [
        {"code": "2510", "name": "LT Debt", "amount": 10.0, "subcategory": "Long-Term Liabilities"},
        {"code": "2010", "name": "AP", "amount": 5.0, "subcategory": "Current Liabilities"},
    ]
    equity = [
        {"code": "3010", "name": "Owner Equity", "amount": 135.0, "subcategory": "Equity"},
    ]
    sections = build_balance_sections(assets, liabilities, equity)

    assert [s["subcategory"] for s in sections["assets"]] == ["Current Assets", "Fixed Assets"]
    assert [line["code"] for line in sections["assets"][0]["lines"]] == ["1010", "1020"]
    assert sections["assets"][0]["total"] == 50.0
    assert sections["assets"][1]["total"] == 100.0
    assert [s["subcategory"] for s in sections["liabilities"]] == [
        "Current Liabilities",
        "Long-Term Liabilities",
    ]
    assert sections["equity"][0]["subcategory"] == "Equity"


def _tx(
    *,
    day: date,
    amount: str,
    tx_type: TransactionType,
    code: str,
    name: str,
    cash_flow_type: str | None = None,
) -> FinancialTransaction:
    return FinancialTransaction(
        tenant_id=uuid.uuid4(),
        transaction_date=day,
        description="test",
        amount=Decimal(amount),
        currency="USD",
        transaction_type=tx_type,
        chart_of_accounts_code=code,
        chart_of_accounts_name=name,
        status=TransactionStatus.VERIFIED,
        cash_flow_type=cash_flow_type,
        metadata=ExtractionMetadata(
            source=DocumentSource.BANK_STATEMENT,
            raw_file_path="x.pdf",
            extraction_model="test",
            confidence_score=1.0,
        ),
    )


@pytest.mark.asyncio
async def test_emit_investing_bumps_non_cash_asset_and_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wid = uuid.uuid4()
    rows = [
        _tx(
            day=date(2025, 4, 1),
            amount="200.00",
            tx_type=TransactionType.INCOME,
            code="4010",
            name="Sales",
        ),
        _tx(
            day=date(2025, 4, 15),
            amount="50.00",
            tx_type=TransactionType.EXPENSE,
            code="5010",
            name="COGS",
        ),
        _tx(
            day=date(2025, 5, 10),
            amount="80.00",
            tx_type=TransactionType.EXPENSE,
            code="1510",
            name="Equipment",
            cash_flow_type="investing",
        ),
    ]
    repo = AsyncMock()
    repo.list_by_tenant_date_range = AsyncMock(return_value=rows)
    repo.list_by_tenant = AsyncMock(return_value=rows)

    coa = {
        "1010": {
            "name": "Cash and Cash Equivalents",
            "account_type": "asset",
            "subcategory": "Current Assets",
        },
        "1020": {
            "name": "Accounts Receivable",
            "account_type": "asset",
            "subcategory": "Current Assets",
        },
        "1510": {"name": "Equipment", "account_type": "asset", "subcategory": "Fixed Assets"},
        "2010": {
            "name": "Accounts Payable",
            "account_type": "liability",
            "subcategory": "Current Liabilities",
        },
        "3010": {"name": "Owner's Equity", "account_type": "equity", "subcategory": "Equity"},
        "3020": {"name": "Retained Earnings", "account_type": "equity", "subcategory": "Equity"},
        "4010": {"name": "Sales Revenue", "account_type": "income", "subcategory": "Operating Revenue"},
        "5010": {"name": "Cost of Goods Sold", "account_type": "cogs", "subcategory": "COGS"},
    }

    uc = EmitPeriodReportsUseCase(transaction_repo=repo)
    monkeypatch.setattr(uc, "_coa_accounts", lambda _tid: coa)
    monkeypatch.setattr(uc, "_prior_retained_earnings", lambda *_a, **_k: Decimal("0"))

    bundle = await uc.execute(wid, fiscal_year="2025")
    assert float(bundle.pnl["grossProfit"]) == 150.0  # 200 revenue - 50 cogs
    assert float(bundle.pnl["grossProfitByMonth"]["04"]) == 150.0
    bs = bundle.balance_sheet
    asset_by_code = {a["code"]: a for a in bs["assets"]}

    assert "1020" in asset_by_code
    assert float(asset_by_code["1020"]["amount"]) == 0.0
    assert float(asset_by_code["1510"]["amount"]) == 80.0
    assert float(asset_by_code["1010"]["amount"]) == 70.0  # 200 - 50 cogs - 80 equipment
    assert float(asset_by_code["1010"]["byMonth"]["04"]) == 150.0  # YTD Apr after revenue-cogs
    assert float(asset_by_code["1010"]["byMonth"]["05"]) == 70.0

    sections = bs["sections"]
    assert sections is not None
    assert [s["subcategory"] for s in sections["assets"]] == ["Current Assets", "Fixed Assets"]
    fixed = next(s for s in sections["assets"] if s["subcategory"] == "Fixed Assets")
    assert any(line["code"] == "1510" and float(line["amount"]) == 80.0 for line in fixed["lines"])
    assert any(s["subcategory"] == "Current Liabilities" for s in sections["liabilities"])
