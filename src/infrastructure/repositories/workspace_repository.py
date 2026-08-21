"""Workspace (clients table) repository."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from src.infrastructure.repositories.supabase_client import get_supabase_client

TABLE = "clients"


class Workspace(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    name: str
    legal_name: str | None = None
    company_tax_id: str | None = None
    currency: str = "USD"
    fiscal_year_start: str = "01-01"
    industry: str | None = None
    timezone: str = "UTC"


class WorkspaceRepository:
    def _from_row(self, row: dict[str, Any]) -> Workspace:
        return Workspace.model_validate(row)

    def _to_row(self, entity: Workspace) -> dict[str, Any]:
        return {
            "id": str(entity.id),
            "name": entity.name,
            "legal_name": entity.legal_name,
            "company_tax_id": entity.company_tax_id,
            "currency": entity.currency,
            "fiscal_year_start": entity.fiscal_year_start,
            "industry": entity.industry,
            "timezone": entity.timezone,
        }

    async def list_all(self) -> list[Workspace]:
        client = get_supabase_client()
        result = client.table(TABLE).select("*").order("created_at", desc=True).execute()
        return [self._from_row(r) for r in result.data]

    async def get(self, workspace_id: uuid.UUID) -> Workspace | None:
        client = get_supabase_client()
        result = (
            client.table(TABLE).select("*").eq("id", str(workspace_id)).limit(1).execute()
        )
        if not result.data:
            return None
        return self._from_row(result.data[0])

    async def save(self, entity: Workspace) -> Workspace:
        client = get_supabase_client()
        result = client.table(TABLE).upsert(self._to_row(entity), on_conflict="id").execute()
        return self._from_row(result.data[0])

    async def delete(self, workspace_id: uuid.UUID) -> bool:
        """Remove workspace and related ledger data (best-effort cascade)."""
        client = get_supabase_client()
        wid = str(workspace_id)
        # Child tables keyed by workspace_id or tenant_id
        for table, col in (
            ("documents", "workspace_id"),
            ("financial_transactions", "tenant_id"),
            ("bank_movements", "tenant_id"),
            ("chart_of_accounts", "tenant_id"),
            ("accounting_periods", "tenant_id"),
            ("general_ledger", "tenant_id"),
        ):
            try:
                client.table(table).delete().eq(col, wid).execute()
            except Exception:
                continue
        result = client.table(TABLE).delete().eq("id", wid).execute()
        return bool(result.data)
