"""QuickBooks-layout Profit and Loss / Balance Sheet (TPC template shape) + Excel export."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock

import openpyxl
import pytest

from src.domain.models.enums import DocumentSource, TransactionStatus, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.reports.qb_layout import (
    basis_footer,
    build_balance_rows,
    build_pnl_rows,
    build_qb_reports,
)
from src.infrastructure.reports.qb_xlsx import report_xlsx_bytes
from src.use_cases.emit_period_reports import (
    MONTH_KEYS,
    EmitPeriodReportsUseCase,
    cumulative_by_month,
)

INC, EXP = TransactionType.INCOME, TransactionType.EXPENSE

COA = {
    "1010": {
        "name": "Chase Business Checking",
        "account_type": "asset",
        "subcategory": "Current Assets",
    },
    "1020": {
        "name": "Accounts Receivable (A/R)",
        "account_type": "asset",
        "subcategory": "Current Assets",
    },
    "1510": {"name": "Equipment", "account_type": "asset", "subcategory": "Fixed Assets"},
    "2050": {
        "name": "Chase Ink Credit Card",
        "account_type": "liability",
        "subcategory": "Current Liabilities",
    },
    "2510": {
        "name": "SBA Loan",
        "account_type": "liability",
        "subcategory": "Long-Term Liabilities",
    },
    "3010": {"name": "Owner's Contributions", "account_type": "equity", "subcategory": "Equity"},
    "3020": {"name": "Retained Earnings", "account_type": "equity", "subcategory": "Equity"},
    "3030": {"name": "Owner's Distributions", "account_type": "equity", "subcategory": "Equity"},
    "4010": {
        "name": "Sales:Phone Repairs",
        "account_type": "income",
        "subcategory": "Operating Revenue",
    },
    "4011": {
        "name": "Sales:Accessories",
        "account_type": "income",
        "subcategory": "Operating Revenue",
    },
    "4030": {"name": "Interest Income", "account_type": "income", "subcategory": "Other Income"},
    "5010": {"name": "Cost of Goods Sold", "account_type": "cogs", "subcategory": "COGS"},
    "6060": {
        "name": "Advertising:Marketing Agency",
        "account_type": "expense",
        "subcategory": "Operating Expenses",
    },
    "6065": {
        "name": "Advertising:Social Media Ads",
        "account_type": "expense",
        "subcategory": "Operating Expenses",
    },
    "6110": {
        "name": "Bank Charges",
        "account_type": "expense",
        "subcategory": "Operating Expenses",
    },
    "6140": {
        "name": "Interest Expense",
        "account_type": "expense",
        "subcategory": "Other Expenses",
    },
}


def _tx(day: date, amount: str, tx_type: TransactionType, code: str) -> FinancialTransaction:
    return FinancialTransaction(
        tenant_id=uuid.uuid4(),
        transaction_date=day,
        description="test",
        amount=Decimal(amount),
        currency="USD",
        transaction_type=tx_type,
        chart_of_accounts_code=code,
        chart_of_accounts_name=code,
        status=TransactionStatus.VERIFIED,
        metadata=ExtractionMetadata(
            source=DocumentSource.BANK_STATEMENT,
            raw_file_path="x.pdf",
            extraction_model="test",
            confidence_score=1.0,
        ),
    )


ROWS = [
    # 2024 — closes into Retained Earnings when viewing 2025
    _tx(date(2024, 3, 1), "5000", INC, "4010"),
    _tx(date(2024, 3, 5), "1200", EXP, "5010"),
    _tx(date(2024, 5, 1), "800", EXP, "1510"),
    _tx(date(2024, 6, 1), "500", EXP, "3030"),
    # 2025
    _tx(date(2025, 1, 10), "7000", INC, "4010"),
    _tx(date(2025, 2, 10), "1500", INC, "4011"),
    _tx(date(2025, 2, 15), "12.50", INC, "4030"),
    _tx(date(2025, 3, 1), "2100", EXP, "5010"),
    _tx(date(2025, 3, 3), "900", EXP, "6060"),
    _tx(date(2025, 3, 9), "350", EXP, "6065"),
    _tx(date(2025, 4, 1), "30", EXP, "6110"),
    _tx(date(2025, 4, 2), "95", EXP, "6140"),
    _tx(date(2025, 6, 1), "1000", EXP, "3030"),
    _tx(date(2025, 6, 2), "250", INC, "3010"),
]


async def _bundle(**kw):
    async def by_range(_wid, *, date_from=None, date_to=None, **_):
        return [
            r
            for r in ROWS
            if (not date_from or str(r.transaction_date) >= date_from)
            and (not date_to or str(r.transaction_date) <= date_to)
        ]

    repo = AsyncMock()
    repo.list_by_tenant_date_range = by_range
    uc = EmitPeriodReportsUseCase(transaction_repo=repo)
    uc._coa_accounts = lambda _tid: COA  # type: ignore[method-assign]
    return await uc.execute(uuid.uuid4(), **kw)


def _by_label(rows: list[dict]) -> dict[str, dict]:
    return {r["label"]: r for r in rows}


def test_cumulative_by_month_running_sum() -> None:
    activity = {mk: 0.0 for mk in MONTH_KEYS}
    activity.update({"01": 10.0, "03": 5.0, "12": 2.0})
    cum = cumulative_by_month(activity)
    assert (cum["01"], cum["02"], cum["03"], cum["11"], cum["12"]) == (10.0, 10.0, 15.0, 15.0, 17.0)


@pytest.mark.asyncio
async def test_pnl_follows_quickbooks_template_sections() -> None:
    bundle = await _bundle(fiscal_year="2025")
    rows = build_pnl_rows(bundle.pnl)
    labels = [r["label"] for r in rows]
    # Template order: Income → COGS → Gross Profit → Expenses → NOI → Other → Net Income
    for a, b in [
        ("Income", "Total Income"),
        ("Total Income", "Cost of Goods Sold"),
        ("Total Cost of Goods Sold", "Gross Profit"),
        ("Gross Profit", "Expenses"),
        ("Total Expenses", "Net Operating Income"),
        ("Net Operating Income", "Other Income"),
        ("Net Other Income", "Net Income"),
    ]:
        assert labels.index(a) < labels.index(b)
    by = _by_label(rows)
    # "Parent:Child" CoA names become QuickBooks sub-account groups
    assert by["Sales"]["kind"] == "header"
    assert by["Total for Sales"]["amount"] == pytest.approx(8500.0)
    assert by["Total for Advertising"]["amount"] == pytest.approx(1250.0)
    assert by["Total Income"]["amount"] == pytest.approx(8500.0)
    assert by["Gross Profit"]["amount"] == pytest.approx(6400.0)
    assert by["Net Operating Income"]["amount"] == pytest.approx(5120.0)
    assert by["Net Other Income"]["amount"] == pytest.approx(-82.5)
    assert by["Net Income"]["amount"] == pytest.approx(bundle.pnl["netIncome"])
    # Interest is Other Income, never operating Income
    income_block = labels[: labels.index("Total Income")]
    assert "Interest Income" not in income_block


@pytest.mark.asyncio
async def test_balance_sheet_is_cumulative_as_of_period_end() -> None:
    bundle = await _bundle(fiscal_year="2025")
    bs = bundle.balance_sheet
    assert bs["asOfDate"] == "2025-12-31"
    by = _by_label(build_balance_rows(bs))
    # Cash carries 2024 activity: 5000-1200-800-500 (2024) + 2025 net movements
    assert by["Chase Business Checking"]["amount"] == pytest.approx(
        3800 - 800 - 500 + (8512.5 - 2100 - 900 - 350 - 30 - 95) - 1000 + 250
    )
    assert by["Total Fixed Assets"]["amount"] == pytest.approx(800.0)
    # Prior year P&L → Retained Earnings; current year → Net Income
    assert by["Retained Earnings"]["amount"] == pytest.approx(3800.0)
    assert by["Net Income"]["amount"] == pytest.approx(5037.5)
    assert by["Owner's Distributions"]["amount"] == pytest.approx(-1500.0)
    assert by["Total Assets"]["amount"] == pytest.approx(bs["totalAssets"])
    assert by["Total Liabilities and Equity"]["amount"] == pytest.approx(
        bs["totalLiabilities"] + bs["totalEquity"]
    )
    # These postings never touch liabilities → the equation must hold
    assert bs["balanced"] is True


@pytest.mark.asyncio
async def test_balance_sheet_template_buckets_and_order() -> None:
    bundle = await _bundle(fiscal_year="2025")
    labels = [r["label"] for r in build_balance_rows(bundle.balance_sheet)]
    expected = [
        "Assets",
        "Current Assets",
        "Bank Accounts",
        "Total Bank Accounts",
        "Accounts Receivable",
        "Total Accounts Receivable",
        "Total Current Assets",
        "Fixed Assets",
        "Total Fixed Assets",
        "Total Assets",
        "Liabilities and Equity",
        "Liabilities",
        "Current Liabilities",
        "Credit Cards",
        "Total Credit Cards",
        "Total Current Liabilities",
        "Long-term Liabilities",
        "Total Long-term Liabilities",
        "Total Liabilities",
        "Equity",
        "Total Equity",
        "Total Liabilities and Equity",
    ]
    positions = [labels.index(x) for x in expected]
    assert positions == sorted(positions)
    eq = labels[labels.index("Equity") + 1 : labels.index("Total Equity")]
    assert eq[-2:] == ["Retained Earnings", "Net Income"]


@pytest.mark.asyncio
async def test_monthly_view_balance_is_as_of_month_end() -> None:
    bundle = await _bundle(fiscal_year="2025", month=2)
    assert bundle.balance_sheet["asOfDate"] == "2025-02-28"
    qb = build_qb_reports(bundle, "My Xcell Network CORP")
    assert qb["profit_and_loss"]["period"] == "February 2025"
    assert qb["balance_sheet"]["period"] == "As of Feb 28, 2025"
    by = _by_label(qb["profit_and_loss"]["rows"])
    assert by["Total Income"]["amount"] == pytest.approx(1500.0)


@pytest.mark.asyncio
async def test_excel_matches_template_layout_with_live_formulas() -> None:
    bundle = await _bundle(fiscal_year="2025")
    qb = build_qb_reports(bundle, "My Xcell Network CORP")
    for key, title, period in (
        ("profit_and_loss", "Profit and Loss", "January-December, 2025"),
        ("balance_sheet", "Balance Sheet", "As of Dec 31, 2025"),
    ):
        data = report_xlsx_bytes(company=qb["company"], report=qb[key], footer="Cash Basis X")
        ws = openpyxl.load_workbook(BytesIO(data)).active
        assert (ws["A1"].value, ws["A2"].value, ws["A3"].value) == (
            "My Xcell Network CORP",
            title,
            period,
        )
        assert ws["B5"].value == "Total"
        assert ws["A6"].value == ("Income" if key == "profit_and_loss" else "Assets")
        rows = qb[key]["rows"]
        for i, row in enumerate(rows):
            cell = ws.cell(row=6 + i, column=2).value
            if row["kind"] == "header":
                assert cell is None
            elif row["kind"] == "account":
                assert cell == pytest.approx(row["amount"])
            else:
                assert isinstance(cell, str) and cell.startswith("=")
        assert ws.cell(row=6 + len(rows) + 3, column=1).value == "Cash Basis X"


def test_basis_footer_shape() -> None:
    text = basis_footer(datetime(2026, 10, 21, 11, 3))
    assert text == "Cash Basis Wednesday, October 21, 2026 11:03 AM"


def test_multi_level_sub_accounts_nest_like_quickbooks() -> None:
    pnl = {
        "revenueItems": [
            {"code": "4010", "name": "Sales", "amount": 1.0, "subcategory": ""},
            {"code": "4011", "name": "Sales:Retail", "amount": 10.0, "subcategory": ""},
            {"code": "4012", "name": "Sales:Retail:Phones", "amount": 7.0, "subcategory": ""},
            {"code": "4020", "name": "Services", "amount": 2.0, "subcategory": ""},
        ]
    }
    rows = build_pnl_rows(pnl)
    labels = [(r["label"], r["depth"], r["kind"]) for r in rows]
    by = _by_label(rows)
    assert ("Sales", 1, "header") in labels
    assert ("Retail", 2, "header") in labels
    assert ("Phones", 3, "account") in labels
    assert by["Total for Retail"]["amount"] == pytest.approx(17.0)
    assert by["Total for Sales"]["amount"] == pytest.approx(18.0)
    assert by["Total Income"]["amount"] == pytest.approx(20.0)
    # Without COGS / Other sections: Gross Profit = Income, Net Income = NOI
    assert by["Gross Profit"]["amount"] == pytest.approx(20.0)
    assert by["Net Income"]["amount"] == pytest.approx(20.0)


@pytest.mark.asyncio
async def test_custom_range_is_not_titled_as_full_year() -> None:
    bundle = await _bundle(date_from="2025-03-01", date_to="2025-06-30")
    qb = build_qb_reports(bundle, "My Xcell Network CORP")
    assert qb["profit_and_loss"]["period"] == "Mar 1, 2025 - Jun 30, 2025"
    assert qb["balance_sheet"]["period"] == "As of Jun 30, 2025"
    # Period P&L excludes Jan–Feb sales; the Balance Sheet still carries them via Net Income
    assert _by_label(qb["profit_and_loss"]["rows"])["Total Income"]["amount"] == pytest.approx(0.0)
    assert _by_label(qb["balance_sheet"]["rows"])["Net Income"]["amount"] == pytest.approx(5037.5)


@pytest.mark.asyncio
async def test_history_query_cannot_truncate_the_period() -> None:
    calls: list[dict] = []

    async def by_range(_wid, *, date_from=None, date_to=None, **kw):
        calls.append({"date_from": date_from, "date_to": date_to, **kw})
        return [
            r
            for r in ROWS
            if (not date_from or str(r.transaction_date) >= date_from)
            and (not date_to or str(r.transaction_date) <= date_to)
        ]

    repo = AsyncMock()
    repo.list_by_tenant_date_range = by_range
    uc = EmitPeriodReportsUseCase(transaction_repo=repo)
    uc._coa_accounts = lambda _tid: COA  # type: ignore[method-assign]
    bundle = await uc.execute(uuid.uuid4(), fiscal_year="2025")
    assert {"date_from": None, "date_to": "2024-12-31"}.items() <= calls[0].items()
    assert (calls[1]["date_from"], calls[1]["date_to"]) == ("2025-01-01", "2025-12-31")
    assert bundle.transaction_count == 10
