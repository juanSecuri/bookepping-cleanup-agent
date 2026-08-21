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
    status: DocumentStatus = DocumentStatus.PROCESSING
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DocumentRepository:
    def _to_row(self, entity: DocumentRecord) -> dict[str, Any]:
        data = entity.model_dump(mode="json")
        data["file_type"] = entity.file_type.value
        data["status"] = entity.status.value
        return data

    def _from_row(self, row: dict[str, Any]) -> DocumentRecord:
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
