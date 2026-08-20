"""
IngestDocument use-case.

Routes a raw document to the correct extraction pipeline:
  photo      → OpenAI vision → FinancialTransaction
  audio      → Groq Whisper + OpenAI structure → FinancialTransaction
  invoice PDF → LlamaParse text + OpenAI structure → FinancialTransaction
  bank PDF   → LlamaParse tables → list[BankMovement] (persisted)
"""
from __future__ import annotations

import uuid
from pathlib import Path

from src.domain.exceptions import ExtractionError
from src.domain.models.bank_movement import BankMovement
from src.domain.models.enums import DocumentSource
from src.domain.models.transaction import FinancialTransaction
from src.infrastructure.llm.openai_client import OpenAIClient
from src.infrastructure.llm.voice_client import VoiceClient
from src.infrastructure.ocr.llama_parse_client import LlamaParseClient
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.transaction_repository import TransactionRepository

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
_PDF_EXTENSION = ".pdf"
_TEXT_EXTENSIONS = {".txt"}


class IngestDocumentUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository | None = None,
        movement_repo: BankMovementRepository | None = None,
        openai_client: OpenAIClient | None = None,
        voice_client: VoiceClient | None = None,
        llama_client: LlamaParseClient | None = None,
    ) -> None:
        self._transactions = transaction_repo or TransactionRepository()
        self._movements = movement_repo or BankMovementRepository()
        self._openai = openai_client or OpenAIClient()
        self._voice = voice_client or VoiceClient(openai_client=self._openai)
        self._llama = llama_client or LlamaParseClient()

    async def execute(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        *,
        bank_name: str | None = None,
        bank_account_number: str | None = None,
        statement_month: str | None = None,
    ) -> FinancialTransaction | list[BankMovement]:
        ext = file_path.suffix.lower()

        if ext in _IMAGE_EXTENSIONS:
            return await self._ingest_image(file_path, tenant_id)

        if ext in _AUDIO_EXTENSIONS:
            return await self._ingest_audio(file_path, tenant_id)

        if ext in _TEXT_EXTENSIONS:
            return await self._ingest_text_file(file_path, tenant_id)

        if ext == _PDF_EXTENSION:
            if bank_name and bank_account_number and statement_month:
                return await self._ingest_bank_statement(
                    file_path, tenant_id, bank_name, bank_account_number, statement_month
                )
            return await self._ingest_invoice_pdf(file_path, tenant_id)

        raise ExtractionError(
            f"Unsupported file type '{ext}'. "
            f"Supported: images {_IMAGE_EXTENSIONS}, audio {_AUDIO_EXTENSIONS}, "
            f"text {_TEXT_EXTENSIONS}, PDF."
        )

    async def _ingest_image(
        self, file_path: Path, tenant_id: uuid.UUID
    ) -> FinancialTransaction:
        tx = await self._openai.extract_from_image(file_path, tenant_id)
        return await self._transactions.save(tx)

    async def _ingest_audio(
        self, file_path: Path, tenant_id: uuid.UUID
    ) -> FinancialTransaction:
        tx = await self._voice.extract_from_audio(file_path, tenant_id)
        return await self._transactions.save(tx)

    async def _ingest_text_file(
        self, file_path: Path, tenant_id: uuid.UUID
    ) -> FinancialTransaction:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        tx = await self._openai.extract_from_text_document(
            text, file_path, tenant_id, source=DocumentSource.MANUAL
        )
        return await self._transactions.save(tx)

    async def _ingest_invoice_pdf(
        self, file_path: Path, tenant_id: uuid.UUID
    ) -> FinancialTransaction:
        text = await self._llama.extract_text(file_path)
        tx = await self._openai.extract_from_text_document(
            text, file_path, tenant_id, source=DocumentSource.PDF
        )
        return await self._transactions.save(tx)

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
        saved: list[BankMovement] = []
        for movement in movements:
            saved.append(await self._movements.save(movement))
        return saved
