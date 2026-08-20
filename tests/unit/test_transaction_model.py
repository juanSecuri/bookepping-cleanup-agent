"""Unit tests for FinancialTransaction domain model validations."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.domain.models.enums import DocumentSource, TransactionStatus, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction


def _metadata(**overrides) -> ExtractionMetadata:
    defaults = dict(
        source=DocumentSource.PHOTO,
        raw_file_path="/tmp/test.jpg",
        extraction_model="gpt-4o",
        confidence_score=0.95,
    )
    return ExtractionMetadata(**(defaults | overrides))


def _transaction(**overrides) -> FinancialTransaction:
    defaults = dict(
        tenant_id=uuid.uuid4(),
        transaction_date=date(2022, 6, 15),
        description="Test expense",
        amount=Decimal("150.00"),
        transaction_type=TransactionType.EXPENSE,
        metadata=_metadata(),
    )
    return FinancialTransaction(**(defaults | overrides))


class TestFinancialTransactionValidation:
    def test_valid_transaction_is_created(self) -> None:
        tx = _transaction()
        assert tx.status == TransactionStatus.PENDING_REVIEW
        assert tx.amount == Decimal("150.00")

    def test_amount_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="amount must be greater than zero"):
            _transaction(amount=Decimal("0"))

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="amount must be greater than zero"):
            _transaction(amount=Decimal("-10"))

    def test_currency_uppercased(self) -> None:
        tx = _transaction(currency="usd")
        assert tx.currency == "USD"

    def test_confidence_without_code_raises(self) -> None:
        with pytest.raises(ValueError, match="category_confidence requires"):
            _transaction(category_confidence=0.9, chart_of_accounts_code=None)

    def test_mark_verified_returns_new_instance(self) -> None:
        tx = _transaction()
        verified = tx.mark_verified("6010", "Office Supplies", 0.92)
        assert verified.status == TransactionStatus.VERIFIED
        assert verified.chart_of_accounts_code == "6010"
        assert verified.chart_of_accounts_name == "Office Supplies"
        assert tx.status == TransactionStatus.PENDING_REVIEW

    def test_mark_closed(self) -> None:
        tx = _transaction().mark_verified("6010", "Office Supplies", 0.9)
        closed = tx.mark_closed("2022-06")
        assert closed.status == TransactionStatus.CLOSED
        assert closed.fiscal_period == "2022-06"

    def test_confidence_rounded_to_4_decimals(self) -> None:
        meta = _metadata(confidence_score=0.123456789)
        assert meta.confidence_score == 0.1235


class TestExtractionMetadataValidation:
    def test_confidence_must_be_0_to_1(self) -> None:
        with pytest.raises(ValueError):
            _metadata(confidence_score=1.5)

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            _metadata(confidence_score=-0.1)
