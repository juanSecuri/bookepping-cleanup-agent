"""
FinancialTransaction — central immutable domain entity.
Every document ingested becomes a FinancialTransaction before being
included in a MonthlyLedger and generating financial statements.
"""
from __future__ import annotations
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from src.domain.models.enums import DocumentSource, TransactionStatus, TransactionType


class ExtractionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: DocumentSource
    raw_file_path: str
    extraction_model: str
    extraction_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    raw_text: str | None = None
    page_number: int | None = Field(default=None, ge=1)

    @field_validator("confidence_score")
    @classmethod
    def round_confidence(cls, v: float) -> float:
        return round(v, 4)


class FinancialTransaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Identity
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID

    # Core accounting
    transaction_date: date
    description: str = Field(..., min_length=1, max_length=512)
    amount: Decimal = Field(..., description="Always positive")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    transaction_type: TransactionType

    # Chart of Accounts (filled by RAG engine)
    chart_of_accounts_code: str | None = None
    chart_of_accounts_name: str | None = None
    category_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    # References
    vendor_name: str | None = Field(default=None, max_length=256)
    tax_id: str | None = Field(default=None, max_length=64)
    invoice_number: str | None = Field(default=None, max_length=128)
    bank_movement_id: uuid.UUID | None = None

    # Period tracking
    fiscal_period: str | None = Field(
        default=None,
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="YYYY-MM — set when transaction is assigned to a closed period",
    )

    # Pipeline state
    status: TransactionStatus = Field(default=TransactionStatus.PENDING_REVIEW)
    metadata: ExtractionMetadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= Decimal("0"):
            raise ValueError("amount must be greater than zero")
        return v

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def category_confidence_requires_code(self) -> "FinancialTransaction":
        if self.category_confidence is not None and self.chart_of_accounts_code is None:
            raise ValueError("category_confidence requires chart_of_accounts_code to be set")
        return self

    def mark_verified(self, chart_code: str, chart_name: str, confidence: float) -> "FinancialTransaction":
        return self.model_copy(update={
            "status": TransactionStatus.VERIFIED,
            "chart_of_accounts_code": chart_code,
            "chart_of_accounts_name": chart_name,
            "category_confidence": round(confidence, 4),
            "updated_at": datetime.now(timezone.utc),
        })

    def mark_closed(self, fiscal_period: str) -> "FinancialTransaction":
        return self.model_copy(update={
            "status": TransactionStatus.CLOSED,
            "fiscal_period": fiscal_period,
            "updated_at": datetime.now(timezone.utc),
        })
