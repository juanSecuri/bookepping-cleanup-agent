"""
IngestDocument use-case.

Orchestrates the full ingestion pipeline for a single raw document:
  photo / PDF → ClaudeVisionClient → FinancialTransaction (pending_review)
  audio       → VoiceClient       → FinancialTransaction (pending_review)
  bank PDF    → LlamaParseClient  → [BankMovement, ...]
"""
from __future__ import annotations

import uuid
from pathlib import Path

from src.domain.exceptions import ExtractionError
from src.domain.models.bank_movement import BankMovement
from src.domain.models.enums import DocumentSource
from src.domain.models.transaction import FinancialTransaction
from src.infrastructure.llm.claude_client import ClaudeVisionClient
from src.infrastructure.llm.voice_client import VoiceClient
from src.infrastructure.ocr.llama_parse_client import LlamaParseClient
from src.infrastructure.repositories.transaction_repository import TransactionRepository

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp"}
_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
_PDF_EXTENSION = ".pdf"


class IngestDocumentUseCase:
    """
    Entry point for adding a new raw document to the bookkeeping pipeline.

    Usage:
        use_case = IngestDocumentUseCase()
        result = await use_case.execute(
            file_path=Path("uploads/factura_2022.jpg"),
            tenant_id=uuid.UUID("..."),
        )
    """

    def __init__(
        self,
        transaction_repo: TransactionRepository | None = None,
        claude_client: ClaudeVisionClient | None = None,
        voice_client: VoiceClient | None = None,
        llama_client: LlamaParseClient | None = None,
    ) -> None:
        self._transaction_repo = transaction_repo or TransactionRepository()
        self._claude = claude_client or ClaudeVisionClient()
        self._voice = voice_client or VoiceClient()
        self._llama = llama_client or LlamaParseClient()

    async def execute(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        *,
        # Bank statement metadata (required when file is a bank PDF)
        bank_name: str | None = None,
        bank_account_number: str | None = None,
        statement_month: str | None = None,
    ) -> FinancialTransaction | list[BankMovement]:
        """
        Auto-detect document type and run the appropriate extraction pipeline.

        Returns:
            - FinancialTransaction for photos / audio
            - list[BankMovement] for bank statement PDFs
        """
        ext = file_path.suffix.lower()

        if ext in _IMAGE_EXTENSIONS:
            return await self._ingest_image(file_path, tenant_id)

        if ext in _AUDIO_EXTENSIONS:
            return await self._ingest_audio(file_path, tenant_id)

        if ext == _PDF_EXTENSION:
            if bank_name and bank_account_number and statement_month:
                return await self._ingest_bank_statement(
                    file_path, tenant_id, bank_name, bank_account_number, statement_month
                )
            # Plain PDF (invoice/receipt) → treat as image via vision model
            return await self._claude.extract_from_image(
                file_path, tenant_id, source=DocumentSource.PDF
            )

        raise ExtractionError(
            f"Unsupported file type '{ext}'. "
            f"Supported: images {_IMAGE_EXTENSIONS}, audio {_AUDIO_EXTENSIONS}, PDF."
        )

    async def _ingest_image(
        self, file_path: Path, tenant_id: uuid.UUID
    ) -> FinancialTransaction:
        tx = await self._claude.extract_from_image(file_path, tenant_id)
        return await self._transaction_repo.save(tx)

    async def _ingest_audio(
        self, file_path: Path, tenant_id: uuid.UUID
    ) -> FinancialTransaction:
        tx = await self._voice.extract_from_audio(file_path, tenant_id)
        return await self._transaction_repo.save(tx)

    async def _ingest_bank_statement(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
    ) -> list[BankMovement]:
        movements = await self._llama.parse_bank_statement(
            file_path, tenant_id, bank_name, bank_account_number, statement_month
        )
        return movements   # Saved by process_statement use-case
