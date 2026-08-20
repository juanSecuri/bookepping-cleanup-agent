"""
Invoice — domain entity for supplier/vendor invoices captured from photos or PDFs.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.models.enums import DocumentSource, TransactionStatus


class InvoiceLineItem(BaseModel):
    """A single line on a vendor invoice."""
    model_config = ConfigDict(frozen=True)

    description: str = Field(..., min_length=1, max_length=512)
    quantity: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    unit_price: Decimal = Field(..., gt=Decimal("0"))
    tax_rate: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("1"))
    chart_of_accounts_code: str | None = None

    @property
    def subtotal(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    @property
    def tax_amount(self) -> Decimal:
        return (self.subtotal * self.tax_rate).quantize(Decimal("0.01"))

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax_amount


class Invoice(BaseModel):
    """
    Supplier invoice captured via photo, PDF or manual entry.

    Relationships:
    - One Invoice → one FinancialTransaction (created after verification)
    - One Invoice → zero or one BankMovement (after reconciliation)
    """
    model_config = ConfigDict(frozen=True)

    # ── Identity ──────────────────────────────────────────────────────────────
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID

    # ── Invoice header ────────────────────────────────────────────────────────
    invoice_number: str = Field(..., min_length=1, max_length=128)
    invoice_date: date
    due_date: date | None = None

    vendor_name: str = Field(..., min_length=1, max_length=256)
    vendor_tax_id: str | None = Field(default=None, max_length=64)
    vendor_address: str | None = Field(default=None, max_length=512)

    # ── Monetary totals ───────────────────────────────────────────────────────
    subtotal: Decimal = Field(..., gt=Decimal("0"))
    tax_total: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    total_amount: Decimal = Field(..., gt=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=3)

    # ── Line items (optional — not always parseable from photos) ─────────────
    line_items: list[InvoiceLineItem] = Field(default_factory=list)

    # ── Provenance & state ────────────────────────────────────────────────────
    source: DocumentSource
    raw_file_path: str
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    status: TransactionStatus = Field(default=TransactionStatus.PENDING_REVIEW)

    # ── Links ─────────────────────────────────────────────────────────────────
    transaction_id: uuid.UUID | None = None
    bank_movement_id: uuid.UUID | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()

    @field_validator("total_amount")
    @classmethod
    def total_must_match_subtotal_plus_tax(cls, v: Decimal, info: Any) -> Decimal:
        # Soft check — extraction models often round differently
        data = info.data
        if "subtotal" in data and "tax_total" in data:
            expected = data["subtotal"] + data["tax_total"]
            if abs(v - expected) > Decimal("0.10"):
                raise ValueError(
                    f"total_amount {v} deviates more than 0.10 from subtotal+tax {expected}"
                )
        return v
