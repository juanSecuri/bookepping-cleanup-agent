"""Document upload tracking repository."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from src.domain.models.enums import DocumentFileType, DocumentStatus
from src.infrastructure.repositories.supabase_client import get_supabase_client

TABLE = "documents"


class DocumentRecord(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID
    file_name: str
    file_type: DocumentFileType
    file_size_bytes: int | None = None
    status: DocumentStatus = DocumentStatus.PENDING
    extraction_confidence: float | None = None
    raw_extracted_text: str | None = None
    error_message: str | None = None
    document_date: str | None = None
    vendor: str | None = None
    drive_file_id: str | None = None
    drive_path: str | None = None
    source: str = "upload"
    pipeline_kind: str | None = None
    apis_used: str | None = None
    folder_group: str | None = None
    local_path: str | None = None
    storage_path: str | None = None
    queue_payload: dict[str, Any] = Field(default_factory=dict)
    processing_started_at: datetime | None = None
    processed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentRepository:
    def _to_row(self, entity: DocumentRecord) -> dict[str, Any]:
        data = entity.model_dump(mode="json")
        data["file_type"] = entity.file_type.value
        data["status"] = entity.status.value
        data["queue_payload"] = entity.queue_payload or {}
        return data

    def _from_row(self, row: dict[str, Any]) -> DocumentRecord:
        payload = row.get("queue_payload")
        if payload is None:
            row = {**row, "queue_payload": {}}
        elif isinstance(payload, str):
            import json

            try:
                row = {**row, "queue_payload": json.loads(payload)}
            except Exception:
                row = {**row, "queue_payload": {}}
        return DocumentRecord.model_validate(row)

    async def save(self, entity: DocumentRecord) -> DocumentRecord:
        client = get_supabase_client()
        result = client.table(TABLE).upsert(self._to_row(entity), on_conflict="id").execute()
        return self._from_row(result.data[0])

    async def list_by_workspace(
        self, workspace_id: uuid.UUID, *, limit: int = 100
    ) -> list[DocumentRecord]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("workspace_id", str(workspace_id))
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [self._from_row(r) for r in result.data]

    async def get_by_id(self, entity_id: uuid.UUID) -> DocumentRecord | None:
        client = get_supabase_client()
        result = (
            client.table(TABLE).select("*").eq("id", str(entity_id)).limit(1).execute()
        )
        if not result.data:
            return None
        return self._from_row(result.data[0])

    async def count_by_status(self, workspace_id: uuid.UUID, status: str) -> int:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("id", count="exact")
            .eq("workspace_id", str(workspace_id))
            .eq("status", status)
            .execute()
        )
        return result.count or len(result.data)

    async def count_queue_global(self) -> dict[str, int]:
        client = get_supabase_client()
        out = {"pending": 0, "processing": 0, "extracted": 0, "failed": 0}
        for status in out:
            result = (
                client.table(TABLE)
                .select("id", count="exact")
                .eq("status", status)
                .execute()
            )
            out[status] = int(result.count or len(result.data or []))
        return out

    async def claim_next_pending(self) -> DocumentRecord | None:
        """Atomically-ish claim oldest pending doc (optimistic: pending → processing)."""
        client = get_supabase_client()
        listed = (
            client.table(TABLE)
            .select("*")
            .eq("status", DocumentStatus.PENDING.value)
            .order("created_at", desc=False)
            .limit(1)
            .execute()
        )
        if not listed.data:
            return None
        row = listed.data[0]
        doc_id = row["id"]
        now = datetime.now(timezone.utc).isoformat()
        updated = (
            client.table(TABLE)
            .update(
                {
                    "status": DocumentStatus.PROCESSING.value,
                    "processing_started_at": now,
                    "error_message": None,
                }
            )
            .eq("id", doc_id)
            .eq("status", DocumentStatus.PENDING.value)
            .execute()
        )
        if not updated.data:
            return None
        return self._from_row(updated.data[0])
