"""
Sequential document queue worker — Render Free safe (1 file at a time).

Upload/Drive only enqueue (status=pending). This worker claims one pending
document, processes it, frees memory, then takes the next. A process-wide
asyncio.Lock guarantees no parallel extractions even if multiple kicks fire.
"""
from __future__ import annotations

import asyncio
import gc
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.domain.models.enums import DocumentFileType, DocumentStatus
from src.infrastructure.repositories.document_repository import DocumentRecord, DocumentRepository

logger = logging.getLogger("ledgerai.queue")

_UPLOAD_DIR = Path(__import__("tempfile").gettempdir()) / "ledgerai_uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def upload_dir() -> Path:
    return _UPLOAD_DIR


class DocumentQueueWorker:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._poll_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def enqueue_file(
        self,
        *,
        workspace_id: uuid.UUID,
        filename: str,
        content: bytes,
        file_type: DocumentFileType,
        source: str = "upload",
        drive_file_id: str | None = None,
        drive_path: str | None = None,
        pipeline_kind: str | None = None,
        apis_used: str | None = None,
        folder_group: str | None = None,
        vendor: str | None = None,
        document_date: str | None = None,
        queue_payload: dict[str, Any] | None = None,
        raw_note: str | None = None,
    ) -> DocumentRecord:
        """Persist bytes to disk + insert document as pending. Does not process."""
        docs = DocumentRepository()
        doc_id = uuid.uuid4()
        suffix = Path(filename).suffix or ".bin"
        local = _UPLOAD_DIR / f"{doc_id}{suffix}"
        local.write_bytes(content)

        doc = DocumentRecord(
            id=doc_id,
            workspace_id=workspace_id,
            file_name=filename,
            file_type=file_type,
            file_size_bytes=len(content),
            status=DocumentStatus.PENDING,
            drive_file_id=drive_file_id,
            drive_path=drive_path,
            source=source,
            pipeline_kind=pipeline_kind,
            apis_used=apis_used,
            folder_group=folder_group,
            vendor=vendor,
            document_date=document_date,
            local_path=str(local),
            queue_payload=queue_payload or {},
            raw_extracted_text=raw_note,
        )
        return await docs.save(doc)

    async def kick(self) -> None:
        """Process the full pending queue sequentially (non-blocking schedule)."""
        asyncio.create_task(self.drain(), name="ledgerai-queue-drain")

    async def drain(self) -> int:
        """Process all pending docs one-by-one. Returns count processed."""
        processed = 0
        async with self._lock:
            while True:
                ok = await self._process_next_unlocked()
                if not ok:
                    break
                processed += 1
                gc.collect()
        if processed:
            logger.info("queue drain finished: %s document(s)", processed)
        return processed

    async def start_polling(self, interval_sec: float = 8.0) -> None:
        if self._poll_task and not self._poll_task.done():
            return
        self._stop.clear()

        async def _loop() -> None:
            logger.info("document queue poller started (interval=%ss)", interval_sec)
            while not self._stop.is_set():
                try:
                    await self.drain()
                except Exception:
                    logger.exception("queue poller error")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=interval_sec)
                except TimeoutError:
                    pass
            logger.info("document queue poller stopped")

        self._poll_task = asyncio.create_task(_loop(), name="ledgerai-queue-poller")

    async def stop_polling(self) -> None:
        self._stop.set()
        if self._poll_task:
            await asyncio.wait([self._poll_task], timeout=5)

    async def queue_stats(self) -> dict[str, int]:
        docs = DocumentRepository()
        return await docs.count_queue_global()

    async def _process_next_unlocked(self) -> bool:
        docs = DocumentRepository()
        claimed = await docs.claim_next_pending()
        if not claimed:
            return False

        logger.info("processing document %s (%s)", claimed.id, claimed.file_name)
        try:
            path = await self._resolve_file(claimed)
            await self._run_pipeline(claimed, path)
        except Exception as exc:
            logger.exception("document %s failed", claimed.id)
            now = datetime.now(timezone.utc)
            failed = claimed.model_copy(
                update={
                    "status": DocumentStatus.FAILED,
                    "error_message": str(exc)[:2000],
                    "processed_at": now,
                }
            )
            await docs.save(failed)
        finally:
            # Drop local upload copies after attempt (Drive can re-download)
            if claimed.source == "upload" and claimed.local_path:
                Path(claimed.local_path).unlink(missing_ok=True)
        return True

    async def _resolve_file(self, doc: DocumentRecord) -> Path:
        if doc.local_path and Path(doc.local_path).exists():
            return Path(doc.local_path)

        if doc.drive_file_id:
            from src.infrastructure.drive.google_drive_client import GoogleDriveClient

            content = GoogleDriveClient().download_bytes(doc.drive_file_id)
            suffix = Path(doc.file_name).suffix or ".bin"
            path = _UPLOAD_DIR / f"{doc.id}{suffix}"
            path.write_bytes(content)
            docs = DocumentRepository()
            await docs.save(doc.model_copy(update={"local_path": str(path)}))
            return path

        raise FileNotFoundError(
            "Archivo no disponible (disco efímero tras reinicio). "
            "Vuelve a subir el documento o reimporta desde Drive."
        )

    async def _run_pipeline(self, doc: DocumentRecord, path: Path) -> None:
        from src.container import get_container

        docs = DocumentRepository()
        container = get_container()
        payload = doc.queue_payload or {}
        kind = doc.pipeline_kind or payload.get("plan_kind") or "invoice"
        apis = doc.apis_used or (
            "pdfplumber (local $0), reglas CoA"
            if kind != "spreadsheet"
            else "Google Drive"
        )
        folder = doc.folder_group
        ftype = doc.file_type
        wid = doc.workspace_id
        now = datetime.now(timezone.utc)

        if kind == "spreadsheet" or ftype == DocumentFileType.CSV:
            preview = (
                path.read_text(encoding="utf-8", errors="ignore")[:4000]
                if ftype == DocumentFileType.CSV
                else (
                    f"Excel registrado ({doc.file_name}). "
                    "Parse tabular completo pendiente."
                )
            )
            updated = doc.model_copy(
                update={
                    "status": DocumentStatus.EXTRACTED,
                    "pipeline_kind": "spreadsheet" if kind == "spreadsheet" else doc.pipeline_kind,
                    "apis_used": apis,
                    "folder_group": folder or doc.folder_group,
                    "raw_extracted_text": preview,
                    "processed_at": now,
                }
            )
        elif kind == "statement":
            bank_name = payload.get("bank_name") or doc.vendor or "Bank"
            account = payload.get("bank_account_number") or "0000"
            month = payload.get("statement_month") or "2026-01"
            report = await container.process_statement.execute(
                path, wid, bank_name, account, month
            )
            updated = doc.model_copy(
                update={
                    "status": DocumentStatus.EXTRACTED,
                    "pipeline_kind": "statement",
                    "apis_used": apis,
                    "folder_group": folder or doc.folder_group,
                    "extraction_confidence": 0.9,
                    "vendor": bank_name,
                    "document_date": (
                        f"{month}-01" if month and len(str(month)) == 7 else month
                    ),
                    "raw_extracted_text": (
                        f"APIs: {apis}\n"
                        f"Banco: {bank_name}  Cuenta: …{account}\n"
                        f"Mes: {month}\n"
                        f"Movimientos extraídos: {report.total_movements} | "
                        f"Categorizados: {report.categorised} | "
                        f"Sin match: {report.unmatched}\n"
                        f"Cola: 1 archivo a la vez (Render Free)\n"
                        f"Destino: Conciliación + Transacciones (espejo)"
                    ),
                    "processed_at": now,
                }
            )
        else:
            result = await container.ingest.execute(path, wid)
            conf = 0.8
            vendor = None
            doc_date = None
            raw = None
            if not isinstance(result, list):
                conf = result.metadata.confidence_score
                vendor = result.vendor_name
                doc_date = str(result.transaction_date)
                raw = (result.metadata.raw_text or "")[:6000] or None
            updated = doc.model_copy(
                update={
                    "status": DocumentStatus.EXTRACTED,
                    "pipeline_kind": doc.pipeline_kind or "invoice",
                    "apis_used": apis,
                    "folder_group": folder or doc.folder_group,
                    "extraction_confidence": conf,
                    "vendor": vendor,
                    "document_date": doc_date,
                    "raw_extracted_text": (
                        f"APIs: {apis}\n"
                        f"Proveedor detectado: {vendor or '—'}\n"
                        f"Fecha: {doc_date or '—'}\n"
                        f"Cola: 1 archivo a la vez (Render Free)\n"
                        f"Destino: Transacciones (pendiente de revisión)\n"
                        f"--- Texto OCR ---\n{raw or '(sin texto)'}"
                    ),
                    "processed_at": now,
                }
            )

        await docs.save(updated)


_worker: DocumentQueueWorker | None = None


def get_document_worker() -> DocumentQueueWorker:
    global _worker
    if _worker is None:
        _worker = DocumentQueueWorker()
    return _worker
