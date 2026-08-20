"""BankMovement — single row extracted from a monthly bank statement."""
from __future__ import annotations
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from src.domain.models.enums import TransactionStatus


class BankMovement(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    bank_account_number: str = Field(..., min_length=4, max_length=64)
    bank_name: str = Field(..., min_length=1, max_length=128)

    movement_date: date
    value_date: date | None = None
    description: str = Field(..., min_length=1, max_length=512)
    reference: str | None = Field(default=None, max_length=256)

    debit_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    credit_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    running_balance: Decimal | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)

    # Categorisation (filled by RAG engine)
    chart_of_accounts_code: str | None = None
    chart_of_accounts_name: str | None = None
    category_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    # Reconciliation
    matched_invoice_id: uuid.UUID | None = None
    matched_transaction_id: uuid.UUID | None = None
    status: TransactionStatus = Field(default=TransactionStatus.PENDING_REVIEW)

    # Provenance
    source_file_path: str
    statement_month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def exactly_one_direction(self) -> "BankMovement":
        if self.debit_amount == Decimal("0") and self.credit_amount == Decimal("0"):
            raise ValueError("A bank movement must have either a debit or a credit amount > 0")
        if self.debit_amount > Decimal("0") and self.credit_amount > Decimal("0"):
            raise ValueError("A bank movement cannot have both debit and credit amounts set")
        return self

    @property
    def net_amount(self) -> Decimal:
        """Positive = credit (money in), negative = debit (money out)."""
        return self.credit_amount - self.debit_amount

    def mark_reconciled(self, invoice_id: uuid.UUID | None = None, transaction_id: uuid.UUID | None = None) -> "BankMovement":
        return self.model_copy(update={
            "matched_invoice_id": invoice_id,
            "matched_transaction_id": transaction_id,
            "status": TransactionStatus.VERIFIED,
        })
