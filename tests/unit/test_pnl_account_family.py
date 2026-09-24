"""P&L must route by CoA code family — never put OpEx/Social Media into INGRESOS."""
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
    resolve_account_type,
)


def _tx(
    *,
    day: date,
    amount: str,
    tx_type: TransactionType,
    code: str,
    name: str,
) -> FinancialTransaction:
    return FinancialTransaction(
        tenant_id=uuid.uuid4(),
        transaction_date=day,
        description=name,
        amount=Decimal(amount),
        currency="USD",
        transaction_type=tx_type,
        chart_of_accounts_code=code,
        chart_of_accounts_name=name,
        status=TransactionStatus.VERIFIED,
        metadata=ExtractionMetadata(
            source=DocumentSource.BANK_STATEMENT,
            raw_file_path="x.pdf",
            extraction_model="test",
            confidence_score=1.0,
        ),
    )


def test_resolve_account_type_prefers_code_family() -> None:
    assert (
        resolve_account_type("6065", None, TransactionType.INCOME) == "expense"
    )
    assert (
        resolve_account_type("4020", "expense", TransactionType.EXPENSE) == "income"
    )
    assert resolve_account_type("5010", None, TransactionType.INCOME) == "cogs"
    assert resolve_account_type("3030", None, TransactionType.EXPENSE) == "equity"


@pytest.mark.asyncio
async def test_social_media_never_in_revenue_even_if_bank_says_income(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wid = uuid.uuid4()
    rows = [
        _tx(
            day=date(2025, 3, 1),
            amount="1000.00",
            tx_type=TransactionType.INCOME,
            code="4020",
            name="Service Revenue",
        ),
        _tx(
            day=date(2025, 3, 2),
            amount="500.00",
            tx_type=TransactionType.INCOME,  # bank flipped — still expense
            code="6065",
            name="Social Media Ads",
        ),
        _tx(
            day=date(2025, 3, 3),
            amount="200.00",
            tx_type=TransactionType.INCOME,
            code="6050",
            name="Travel & Meals",
        ),
        _tx(
            day=date(2025, 3, 4),
            amount="50.00",
            tx_type=TransactionType.EXPENSE,
            code="6100",
            name="Technology & Software",
        ),
    ]
    repo = AsyncMock()
    repo.list_by_tenant_date_range = AsyncMock(return_value=rows)
    repo.list_by_tenant = AsyncMock(return_value=rows)

    uc = EmitPeriodReportsUseCase(transaction_repo=repo)
    monkeypatch.setattr(
        uc,
        "_coa_accounts",
        lambda _tid: {
            "4020": {"name": "Service Revenue", "account_type": "income", "subcategory": ""},
            "6065": {
                "name": "Social Media Ads",
                "account_type": "expense",
                "subcategory": "",
            },
            "6050": {"name": "Travel & Meals", "account_type": "expense", "subcategory": ""},
            "6100": {
                "name": "Technology & Software",
                "account_type": "expense",
                "subcategory": "",
            },
            "1010": {
                "name": "Cash",
                "account_type": "asset",
                "subcategory": "Current Assets",
            },
        },
    )
    monkeypatch.setattr(uc, "_prior_retained_earnings", lambda *_a, **_k: Decimal("0"))

    bundle = await uc.execute(workspace_id=wid, period="2025")
    rev_codes = {r["code"] for r in bundle.pnl["revenueItems"]}
    exp_codes = {r["code"] for r in bundle.pnl["expenseItems"]}

    assert rev_codes == {"4020"}
    assert "6065" not in rev_codes
    assert "6050" not in rev_codes
    assert "6065" in exp_codes
    assert "6050" in exp_codes
    assert "6100" in exp_codes
    assert float(bundle.pnl["totalRevenue"]) == pytest.approx(1000.0)
    assert float(bundle.pnl["totalExpenses"]) == pytest.approx(750.0)
