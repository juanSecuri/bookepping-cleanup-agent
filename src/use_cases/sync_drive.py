"""Sync Google Drive folders into LedgerAI documents + ingest pipeline."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from src.domain.models.enums import DocumentFileType, DocumentStatus
from src.infrastructure.drive.google_drive_client import (
    DriveNotConfiguredError,
    GoogleDriveClient,
    credentials_available,
)
from src.infrastructure.repositories.document_repository import DocumentRecord, DocumentRepository
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.workspace_repository import WorkspaceRepository


def _file_type(name: str, mime: str) -> DocumentFileType:
    lower = name.lower()
    if mime.startswith("image/") or lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return DocumentFileType.IMAGE
    if mime == "application/pdf" or lower.endswith(".pdf"):
        return DocumentFileType.PDF
    if mime == "text/csv" or lower.endswith(".csv"):
        return DocumentFileType.CSV
    if lower.endswith((".xlsx", ".xls")) or "spreadsheet" in mime:
        return DocumentFileType.OTHER
    if mime.startswith("audio/") or lower.endswith((".mp3", ".wav", ".m4a", ".ogg", ".webm")):
        return DocumentFileType.AUDIO
    return DocumentFileType.OTHER


class SyncDriveUseCase:
    def __init__(self) -> None:
        self._docs = DocumentRepository()
        self._workspaces = WorkspaceRepository()

    def status(self) -> dict:
        return {
            "configured": credentials_available(),
            "default_folder_id": "1db-aXczr9hHkv207U5gjEDmUfitN8MmT",
            "default_folder_name": "My Xcell Network CORP",
        }

    async def link_workspace(self, workspace_id: uuid.UUID, folder_id: str, folder_name: str | None = None) -> dict:
        ws = await self._workspaces.get(workspace_id)
        if not ws:
            raise ValueError("Workspace not found")
        client = get_supabase_client()
        client.table("clients").update(
            {
                "drive_folder_id": folder_id,
                "drive_folder_name": folder_name or folder_id,
            }
        ).eq("id", str(workspace_id)).execute()
        return {"workspace_id": str(workspace_id), "drive_folder_id": folder_id, "drive_folder_name": folder_name}

    async def browse(self, folder_id: str, depth: int = 2) -> dict:
        if not credentials_available():
            raise DriveNotConfiguredError("Drive OAuth not configured")
        return GoogleDriveClient().browse_tree(folder_id, depth=depth)

    async def sync(
        self,
        workspace_id: uuid.UUID,
        *,
        folder_id: str | None = None,
        max_files: int = 30,
        ingest: bool = True,
    ) -> dict:
        if not credentials_available():
            raise DriveNotConfiguredError("Drive OAuth not configured")

        ws = await self._workspaces.get(workspace_id)
        if not ws:
            raise ValueError("Workspace not found")

        root_id = folder_id
        if not root_id:
            client = get_supabase_client()
            row = (
                client.table("clients")
                .select("drive_folder_id,drive_folder_name")
                .eq("id", str(workspace_id))
                .limit(1)
                .execute()
            )
            if row.data and row.data[0].get("drive_folder_id"):
                root_id = row.data[0]["drive_folder_id"]
            else:
                root_id = "1db-aXczr9hHkv207U5gjEDmUfitN8MmT"

        assert root_id
        drive = GoogleDriveClient()
        existing = await self._docs.list_by_workspace(workspace_id, limit=2000)
        known_ids = {d.drive_file_id for d in existing if d.drive_file_id}

        discovered = 0
        imported = 0
        skipped = 0
        failed: list[dict] = []
        imported_docs: list[dict] = []

        from src.container import get_container

        container = get_container()
        upload_dir = Path(tempfile.gettempdir()) / "ledgerai_drive"
        upload_dir.mkdir(parents=True, exist_ok=True)

        for node in drive.walk_ingestible(root_id, max_files=max_files):
            discovered += 1
            if node.id in known_ids:
                skipped += 1
                continue
            try:
                content = drive.download_bytes(node.id)
                suffix = Path(node.name).suffix or ".bin"
                tmp = upload_dir / f"{node.id}{suffix}"
                tmp.write_bytes(content)

                doc = DocumentRecord(
                    workspace_id=workspace_id,
                    file_name=node.name,
                    file_type=_file_type(node.name, node.mime_type),
                    file_size_bytes=len(content),
                    status=DocumentStatus.PROCESSING,
                    drive_file_id=node.id,
                    drive_path=node.path,
                    source="google_drive",
                )
                doc = await self._docs.save(doc)

                if ingest and doc.file_type != DocumentFileType.CSV:
                    try:
                        result = await container.ingest.execute(tmp, workspace_id)
                        conf = 0.8
                        vendor = None
                        doc_date = None
                        if not isinstance(result, list):
                            conf = result.metadata.confidence_score
                            vendor = result.vendor_name
                            doc_date = str(result.transaction_date)
                            if result.chart_of_accounts_code:
                                await container.transactions.save(
                                    result.model_copy(
                                        update={
                                            "ai_suggested_account_code": result.chart_of_accounts_code,
                                            "ai_suggested_account_name": result.chart_of_accounts_name,
                                        }
                                    )
                                )
                        doc = doc.model_copy(
                            update={
                                "status": DocumentStatus.EXTRACTED,
                                "extraction_confidence": conf,
                                "vendor": vendor,
                                "document_date": doc_date,
                            }
                        )
                    except Exception as exc:
                        doc = doc.model_copy(
                            update={
                                "status": DocumentStatus.FAILED,
                                "error_message": str(exc)[:500],
                            }
                        )
                        failed.append({"file": node.path, "error": str(exc)[:300]})
                else:
                    doc = doc.model_copy(update={"status": DocumentStatus.EXTRACTED})

                doc = await self._docs.save(doc)
                imported += 1
                imported_docs.append(
                    {
                        "id": str(doc.id),
                        "file_name": doc.file_name,
                        "drive_path": doc.drive_path,
                        "status": doc.status.value,
                    }
                )
                tmp.unlink(missing_ok=True)
                known_ids.add(node.id)
            except Exception as exc:
                failed.append({"file": node.path, "error": str(exc)[:300]})

        return {
            "folder_id": root_id,
            "discovered": discovered,
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "documents": imported_docs,
        }
