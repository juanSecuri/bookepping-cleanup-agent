"""Integration test for ReconcileLedger use-case with an in-memory mock repository."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.domain.models.bank_movement import BankMovement
from src.domain.models.enums import DocumentSource, TransactionStatus, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.use_cases.reconcile_ledger import ReconcileLedgerUseCase


def _make_transaction(
    tenant_id: uuid.UUID,
    amount: Decimal,
    txn_date: date,
) -> FinancialTransaction:
    return FinancialTransaction(
        tenant_id=tenant_id,
        transaction_date=txn_date,
        description="Test invoice",
        amount=amount,
        transaction_type=TransactionType.EXPENSE,
        metadata=ExtractionMetadata(
            source=DocumentSource.PHOTO,
            raw_file_path="/tmp/inv.jpg",
            extraction_model="claude-3-5-sonnet",
            confidence_score=0.9,
        ),
    )


def _make_movement(
    tenant_id: uuid.UUID,
    debit: Decimal,
    movement_date: date,
) -> BankMovement:
    return BankMovement(
        tenant_id=tenant_id,
        bank_account_number="999",
        bank_name="TestBank",
        movement_date=movement_date,
        description="Cargo factura",
        debit_amount=debit,
        credit_amount=Decimal("0"),
        source_file_path="/tmp/stmt.pdf",
        statement_month=movement_date.strftime("%Y-%m"),
    )


@pytest.mark.asyncio
async def test_exact_match_reconciles() -> None:
    tenant_id = uuid.uuid4()
    amount = Decimal("500.00")
    txn_date = date(2022, 6, 10)

    transaction = _make_transaction(tenant_id, amount, txn_date)
    movement = _make_movement(tenant_id, amount, txn_date)

    mock_repo = AsyncMock()
    mock_repo.list_pending.return_value = [transaction]
    mock_repo.save.side_effect = lambda x: x

    use_case = ReconcileLedgerUseCase(transaction_repo=mock_repo)
    result = await use_case.execute(tenant_id, [movement])

    assert len(result.matched) == 1
    assert len(result.unmatched_movements) == 0


@pytest.mark.asyncio
async def test_no_match_goes_to_unmatched() -> None:
    tenant_id = uuid.uuid4()
    transaction = _make_transaction(tenant_id, Decimal("500.00"), date(2022, 6, 10))
    movement = _make_movement(tenant_id, Decimal("9999.00"), date(2022, 6, 10))

    mock_repo = AsyncMock()
    mock_repo.list_pending.return_value = [transaction]
    mock_repo.save.side_effect = lambda x: x

    use_case = ReconcileLedgerUseCase(transaction_repo=mock_repo)
    result = await use_case.execute(tenant_id, [movement])

    assert len(result.matched) == 0
    assert len(result.unmatched_movements) == 1


@pytest.mark.asyncio
async def test_date_window_respected() -> None:
    tenant_id = uuid.uuid4()
    amount = Decimal("100.00")
    transaction = _make_transaction(tenant_id, amount, date(2022, 6, 1))
    # Movement is 10 days away — outside the default 3-day window
    movement = _make_movement(tenant_id, amount, date(2022, 6, 11))

    mock_repo = AsyncMock()
    mock_repo.list_pending.return_value = [transaction]
    mock_repo.save.side_effect = lambda x: x

    use_case = ReconcileLedgerUseCase(transaction_repo=mock_repo)
    result = await use_case.execute(tenant_id, [movement])

    assert len(result.unmatched_movements) == 1
