"""
Supabase-backed repository for MonthlyLedger aggregates.

Table expected in Supabase (PostgreSQL):

  CREATE TABLE monthly_ledgers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    fiscal_period   TEXT NOT NULL,        -- YYYY-MM
    currency        CHAR(3) NOT NULL DEFAULT 'USD',
    entries         JSONB NOT NULL DEFAULT '[]',
    transaction_count INT NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'open',
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, fiscal_period)
  );

See migrations/001_initial_schema.sql for the full DDL.
"""
from __future__ import annotations

import uuid
from typing import Any

from src.domain.models.monthly_ledger import MonthlyLedger
from src.infrastructure.repositories.base import AbstractRepository
from src.infrastructure.repositories.supabase_client import get_supabase_client

TABLE = "monthly_ledgers"


class MonthlyLedgerRepository(AbstractRepository[MonthlyLedger]):
    """Concrete Supabase repository for MonthlyLedger closed-period aggregates."""

    # ── serialisation helpers ──────────────────────────────────────────────

    def _to_row(self, entity: MonthlyLedger) -> dict[str, Any]:
        data = entity.model_dump(mode="json")
        # entries is a list[LedgerEntry] → already serialised to dicts by model_dump
        # Ensure Decimal values are stored as strings to avoid float drift
        for entry in data.get("entries", []):
            for key in ("total_debit", "total_credit"):
                if key in entry:
                    entry[key] = str(entry[key])
        return data

    def _from_row(self, row: dict[str, Any]) -> MonthlyLedger:
        return MonthlyLedger.model_validate(row)

    # ── AbstractRepository implementation ─────────────────────────────────

    async def save(self, entity: MonthlyLedger) -> MonthlyLedger:
        client = get_supabase_client()
        row = self._to_row(entity)
        result = (
            client.table(TABLE)
            .upsert(row, on_conflict="id")
            .execute()
        )
        return self._from_row(result.data[0])

    async def get_by_id(self, entity_id: uuid.UUID) -> MonthlyLedger | None:
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
    ) -> list[MonthlyLedger]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .order("fiscal_period", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [self._from_row(r) for r in result.data]

    async def delete(self, entity_id: uuid.UUID) -> None:
        client = get_supabase_client()
        client.table(TABLE).delete().eq("id", str(entity_id)).execute()

    # ── Domain-specific queries ────────────────────────────────────────────

    async def get_by_period(
        self,
        tenant_id: uuid.UUID,
        fiscal_period: str,
    ) -> MonthlyLedger | None:
        """Fetch a ledger for a specific YYYY-MM period."""
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("fiscal_period", fiscal_period)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return self._from_row(result.data[0])

    async def list_closed_periods(
        self,
        tenant_id: uuid.UUID,
        *,
        from_period: str | None = None,
        to_period: str | None = None,
    ) -> list[MonthlyLedger]:
        """
        Return all CLOSED ledgers for a tenant, optionally filtered to a
        fiscal period range (inclusive).  Periods are YYYY-MM strings —
        lexicographic ordering works because they're zero-padded.
        """
        client = get_supabase_client()
        query = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("status", "closed")
            .order("fiscal_period", desc=False)
        )
        if from_period:
            query = query.gte("fiscal_period", from_period)
        if to_period:
            query = query.lte("fiscal_period", to_period)
        result = query.execute()
        return [self._from_row(r) for r in result.data]

    async def list_open_periods(self, tenant_id: uuid.UUID) -> list[MonthlyLedger]:
        """Return all periods that are NOT yet closed (still editable)."""
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("status", "open")
            .order("fiscal_period", desc=False)
            .execute()
        )
        return [self._from_row(r) for r in result.data]
