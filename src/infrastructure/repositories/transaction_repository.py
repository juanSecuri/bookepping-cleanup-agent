"""
Supabase-backed repository for FinancialTransaction entities.

Table expected in Supabase (PostgreSQL):

  CREATE TABLE financial_transactions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    transaction_date DATE NOT NULL,
    description     TEXT NOT NULL,
    amount          NUMERIC(18,4) NOT NULL CHECK (amount > 0),
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    transaction_type TEXT NOT NULL,
    chart_of_accounts_code TEXT,
    category_confidence FLOAT,
    vendor_name     TEXT,
    tax_id          TEXT,
    invoice_number  TEXT,
    bank_movement_id UUID,
    status          TEXT NOT NULL DEFAULT 'pending_review',
    quickbooks_id   TEXT,
    metadata        JSONB NOT NULL,
    extra           JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  );
"""
from __future__ import annotations

import uuid
from typing import Any

from src.domain.models.transaction import FinancialTransaction
from src.infrastructure.repositories.base import AbstractRepository
from src.infrastructure.repositories.supabase_client import get_supabase_client

TABLE = "financial_transactions"


class TransactionRepository(AbstractRepository[FinancialTransaction]):
    """Concrete Supabase repository for FinancialTransaction."""

    def _to_row(self, entity: FinancialTransaction) -> dict[str, Any]:
        raw = entity.model_dump(mode="json")
        # Flatten metadata into a JSONB column
        raw["metadata"] = entity.metadata.model_dump(mode="json")
        return raw

    def _from_row(self, row: dict[str, Any]) -> FinancialTransaction:
        return FinancialTransaction.model_validate(row)

    async def save(self, entity: FinancialTransaction) -> FinancialTransaction:
        client = get_supabase_client()
        row = self._to_row(entity)
        result = (
            client.table(TABLE)
            .upsert(row, on_conflict="id")
            .execute()
        )
        return self._from_row(result.data[0])

    async def get_by_id(self, entity_id: uuid.UUID) -> FinancialTransaction | None:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("id", str(entity_id))
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return self._from_row(result.data[0])

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FinancialTransaction]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .order("transaction_date", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [self._from_row(r) for r in result.data]

    async def list_pending(self, tenant_id: uuid.UUID) -> list[FinancialTransaction]:
        """Return all records still awaiting human review."""
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("status", "pending_review")
            .order("transaction_date", desc=False)
            .execute()
        )
        return [self._from_row(r) for r in result.data]

    async def delete(self, entity_id: uuid.UUID) -> None:
        client = get_supabase_client()
        client.table(TABLE).delete().eq("id", str(entity_id)).execute()
