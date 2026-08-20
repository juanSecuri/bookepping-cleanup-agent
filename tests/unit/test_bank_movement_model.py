"""Unit tests for BankMovement domain model validations."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from src.domain.models.bank_movement import BankMovement


def _movement(**overrides) -> BankMovement:
    defaults = dict(
        tenant_id=uuid.uuid4(),
        bank_account_number="123-456789",
        bank_name="Bancolombia",
        movement_date="2022-06-15",
        description="PAGO NOMINA JUNIO",
        debit_amount=Decimal("5000000"),
        credit_amount=Decimal("0"),
        source_file_path="/tmp/statement.pdf",
        statement_month="2022-06",
    )
    return BankMovement(**(defaults | overrides))


class TestBankMovementValidation:
    def test_valid_debit_movement(self) -> None:
        m = _movement()
        assert m.net_amount == Decimal("-5000000")

    def test_valid_credit_movement(self) -> None:
        m = _movement(debit_amount=Decimal("0"), credit_amount=Decimal("1000"))
        assert m.net_amount == Decimal("1000")

    def test_both_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="must have either a debit or a credit"):
            _movement(debit_amount=Decimal("0"), credit_amount=Decimal("0"))

    def test_both_nonzero_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot have both"):
            _movement(debit_amount=Decimal("100"), credit_amount=Decimal("100"))

    def test_invalid_statement_month_format(self) -> None:
        with pytest.raises(ValueError):
            _movement(statement_month="2022-13")

    def test_mark_reconciled(self) -> None:
        m = _movement()
        txn_id = uuid.uuid4()
        reconciled = m.mark_reconciled(transaction_id=txn_id)
        assert reconciled.matched_transaction_id == txn_id
        assert m.matched_transaction_id is None   # original unchanged
