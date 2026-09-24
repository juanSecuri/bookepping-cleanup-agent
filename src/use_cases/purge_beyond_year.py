"""Remove documents / movements / transactions after a workspace fiscal-year cutoff.

Does NOT wipe the workspace — keeps ≤ max_year. Requires an explicit ceiling
(from the request or clients.max_fiscal_year).
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from src.infrastructure.drive.year_policy import parse_max_fiscal_year, year_from_drive_path
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.workspace_repository import WorkspaceRepository

YEAR_IN_TEXT = re.compile(r"(?:^|/)(20\d{2})(?:/|$)|(?:^|\b)(20\d{2})(?:\b|$)")


def _doc_year(row: dict[str, Any]) -> int | None:
    for text in (
        row.get("folder_group"),
        row.get("drive_path"),
        row.get("file_name"),
        row.get("document_date"),
    ):
        if not text:
            continue
        y = year_from_drive_path(str(text), None)
        if y is not None:
            return y
        m = YEAR_IN_TEXT.search(str(text).replace("\\", "/"))
        if m:
            return int(m.group(1) or m.group(2))
    return None


class PurgeBeyondYearUseCase:
    def __init__(self) -> None:
        self._workspaces = WorkspaceRepository()

    async def execute(
        self,
        workspace_id: uuid.UUID,
        *,
        max_year: int | None = None,
        persist_ceiling: bool = True,
    ) -> dict[str, Any]:
        ws = await self._workspaces.get(workspace_id)
        if not ws:
            raise ValueError("Workspace not found")

        ceiling = parse_max_fiscal_year(max_year)
        if ceiling is None:
            ceiling = parse_max_fiscal_year(ws.max_fiscal_year)
        if ceiling is None:
            raise ValueError(
                "max_fiscal_year is required (set it on the workspace or pass it in the request)"
            )

        if persist_ceiling and ws.max_fiscal_year != ceiling:
            await self._workspaces.update_max_fiscal_year(workspace_id, ceiling)

        after = f"{ceiling + 1}-01-01"
        tid = str(workspace_id)
        client = get_supabase_client()

        tx_del = (
            client.table("financial_transactions")
            .delete()
            .eq("tenant_id", tid)
            .gte("transaction_date", after)
            .execute()
        )
        mv_del = (
            client.table("bank_movements")
            .delete()
            .eq("tenant_id", tid)
            .gte("movement_date", after)
            .execute()
        )

        periods = (
            client.table("statement_periods")
            .select("id,statement_month")
            .eq("tenant_id", tid)
            .execute()
        )
        period_ids = [
            r["id"]
            for r in (periods.data or [])
            if str(r.get("statement_month") or "")[:4].isdigit()
            and int(str(r.get("statement_month"))[:4]) > ceiling
        ]
        periods_deleted = 0
        for pid in period_ids:
            client.table("statement_periods").delete().eq("id", pid).execute()
            periods_deleted += 1

        docs = (
            client.table("documents")
            .select("id,folder_group,drive_path,file_name,document_date")
            .eq("workspace_id", tid)
            .limit(5000)
            .execute()
        )
        doc_ids = [r["id"] for r in (docs.data or []) if (_doc_year(r) or 0) > ceiling]
        docs_deleted = 0
        for did in doc_ids:
            client.table("documents").delete().eq("id", did).execute()
            docs_deleted += 1

        all_mv = (
            client.table("bank_movements")
            .select("id,statement_month")
            .eq("tenant_id", tid)
            .limit(20000)
            .execute()
        )
        extra_mv = [
            r["id"]
            for r in (all_mv.data or [])
            if str(r.get("statement_month") or "")[:4].isdigit()
            and int(str(r.get("statement_month"))[:4]) > ceiling
        ]
        for mid in extra_mv:
            client.table("bank_movements").delete().eq("id", mid).execute()

        return {
            "workspace_id": tid,
            "max_year": ceiling,
            "deleted_transactions": len(tx_del.data or []),
            "deleted_movements": len(mv_del.data or []) + len(extra_mv),
            "deleted_documents": docs_deleted,
            "deleted_statement_periods": periods_deleted,
            "kept_through": str(ceiling),
        }
