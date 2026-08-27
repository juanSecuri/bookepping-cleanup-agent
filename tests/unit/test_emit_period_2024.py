"""Regression: period reports must include older years (not truncated by PostgREST page size)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.domain.models.enums import DocumentSource, TransactionStatus, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.use_cases.emit_period_reports import EmitPeriodReportsUseCase


def _tx(
    *,
    day: date,
    amount: str,
    tx_type: TransactionType,
    status: TransactionStatus = TransactionStatus.VERIFIED,
    code: str = "4000",
    name: str = "Revenue",
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
        status=status,
        metadata=ExtractionMetadata(
            source=DocumentSource.BANK_STATEMENT,
            raw_file_path="x.pdf",
            extraction_model="test",
            confidence_score=1.0,
        ),
    )


@pytest.mark.asyncio
async def test_emit_2024_uses_date_range_query(monkeypatch: pytest.MonkeyPatch) -> None:
    wid = uuid.uuid4()
    rows = [
        _tx(day=date(2024, 3, 10), amount="100.00", tx_type=TransactionType.INCOME),
        _tx(
            day=date(2024, 6, 1),
            amount="40.00",
            tx_type=TransactionType.EXPENSE,
            code="6000",
            name="OpEx",
        ),
        _tx(day=date(2025, 1, 5), amount="999.00", tx_type=TransactionType.INCOME),
    ]
    repo = AsyncMock()
    repo.list_by_tenant_date_range = AsyncMock(
        return_value=[r for r in rows if r.transaction_date.year == 2024]
    )
    repo.list_by_tenant = AsyncMock(return_value=rows)

    # Avoid live CoA / RE lookups
    uc = EmitPeriodReportsUseCase(transaction_repo=repo)
    monkeypatch.setattr(uc, "_coa_types", lambda _tid: {"4000": "income", "6000": "expense"})
    monkeypatch.setattr(uc, "_prior_retained_earnings", lambda *_a, **_k: Decimal("0"))

    bundle = await uc.execute(wid, fiscal_year="2024")
    assert bundle.transaction_count == 2
    assert float(bundle.pnl.get("totalRevenue") or bundle.pnl.get("revenue") or 0) == 100.0
    repo.list_by_tenant_date_range.assert_awaited()
    call_kw = repo.list_by_tenant_date_range.await_args.kwargs
    assert call_kw["date_from"] == "2024-01-01"
    assert call_kw["date_to"] == "2024-12-31"
