"""
Supabase-backed repository for BankMovement entities.

Table: bank_movements  (see migrations/001_initial_schema.sql)
"""
from __future__ import annotations

import uuid
from typing import Any

from src.domain.models.bank_movement import BankMovement
from src.infrastructure.repositories.base import AbstractRepository
from src.infrastructure.repositories.supabase_client import get_supabase_client

TABLE = "bank_movements"


class BankMovementRepository(AbstractRepository[BankMovement]):
    """Concrete Supabase repository for BankMovement entities."""

    def _to_row(self, entity: BankMovement) -> dict[str, Any]:
        data = entity.model_dump(mode="json")
        for key in ("debit_amount", "credit_amount", "running_balance"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        return data

    def _from_row(self, row: dict[str, Any]) -> BankMovement:
        return BankMovement.model_validate(row)

    async def save(self, entity: BankMovement) -> BankMovement:
        client = get_supabase_client()
        row = self._to_row(entity)
        result = client.table(TABLE).upsert(row, on_conflict="id").execute()
        return self._from_row(result.data[0])

    async def get_by_id(self, entity_id: uuid.UUID) -> BankMovement | None:
        client = get_supabase_client()
        result = (
            client.table(TABLE).select("*").eq("id", str(entity_id)).limit(1).execute()
        )
        if not result.data:
            return None
        return self._from_row(result.data[0])

    async def list_by_tenant(
        self,
        tenant_id: uuid.UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[BankMovement]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .order("movement_date", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        return [self._from_row(r) for r in result.data]

    async def delete(self, entity_id: uuid.UUID) -> None:
        client = get_supabase_client()
        client.table(TABLE).delete().eq("id", str(entity_id)).execute()

    # ── Domain-specific queries ────────────────────────────────────────────

    async def list_by_period(
        self, tenant_id: uuid.UUID, statement_month: str
    ) -> list[BankMovement]:
        """All movements for a specific statement month (YYYY-MM)."""
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("statement_month", statement_month)
            .order("movement_date", desc=False)
            .execute()
        )
        return [self._from_row(r) for r in result.data]

    async def list_unreconciled(self, tenant_id: uuid.UUID) -> list[BankMovement]:
        """All movements still in pending_review status."""
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("status", "pending_review")
            .order("movement_date", desc=False)
            .execute()
        )
        return [self._from_row(r) for r in result.data]
