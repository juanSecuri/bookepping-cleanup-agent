"""Unit tests for Invoice domain model validations."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from src.domain.models.enums import DocumentSource
from src.domain.models.invoice import Invoice


def _invoice(**overrides) -> Invoice:
    defaults = dict(
        tenant_id=uuid.uuid4(),
        invoice_number="FAC-2022-001",
        invoice_date="2022-06-01",
        vendor_name="Proveedor S.A.S",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("19.00"),
        total_amount=Decimal("119.00"),
        source=DocumentSource.PHOTO,
        raw_file_path="/tmp/factura.jpg",
        confidence_score=0.92,
    )
    return Invoice(**(defaults | overrides))


class TestInvoiceValidation:
    def test_valid_invoice_created(self) -> None:
        inv = _invoice()
        assert inv.vendor_name == "Proveedor S.A.S"

    def test_total_deviation_raises(self) -> None:
        with pytest.raises(ValueError, match="deviates more than 0.10"):
            _invoice(subtotal=Decimal("100.00"), tax_total=Decimal("0"), total_amount=Decimal("200.00"))

    def test_currency_uppercased(self) -> None:
        inv = _invoice(currency="cop")
        assert inv.currency == "COP"
