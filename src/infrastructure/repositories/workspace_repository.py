"""Workspace (clients table) repository."""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from src.infrastructure.drive.year_policy import parse_max_fiscal_year
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
    # NULL = no ingest/purge year cutoff for this workspace
    max_fiscal_year: int | None = None
    drive_folder_id: str | None = None
    drive_folder_name: str | None = None


class WorkspaceRepository:
    def _from_row(self, row: dict[str, Any]) -> Workspace:
        data = dict(row)
        data["max_fiscal_year"] = parse_max_fiscal_year(data.get("max_fiscal_year"))
        return Workspace.model_validate(data)

    def _to_row(self, entity: Workspace) -> dict[str, Any]:
        row: dict[str, Any] = {
            "id": str(entity.id),
            "name": entity.name,
            "legal_name": entity.legal_name,
            "company_tax_id": entity.company_tax_id,
            "currency": entity.currency,
            "fiscal_year_start": entity.fiscal_year_start,
            "industry": entity.industry,
            "timezone": entity.timezone,
            "max_fiscal_year": entity.max_fiscal_year,
        }
        if entity.drive_folder_id is not None:
            row["drive_folder_id"] = entity.drive_folder_id
        if entity.drive_folder_name is not None:
            row["drive_folder_name"] = entity.drive_folder_name
        return row

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

    async def update_max_fiscal_year(
        self, workspace_id: uuid.UUID, max_fiscal_year: int | None
    ) -> Workspace | None:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .update({"max_fiscal_year": max_fiscal_year})
            .eq("id", str(workspace_id))
            .execute()
        )
        if not result.data:
            return await self.get(workspace_id)
        return self._from_row(result.data[0])

    async def delete(self, workspace_id: uuid.UUID) -> bool:
        """Remove workspace and related ledger data (best-effort cascade)."""
        client = get_supabase_client()
        wid = str(workspace_id)
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
