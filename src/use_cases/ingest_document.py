"""
IngestDocument use-case.

Default EXTRACTION_MODE=local ($0):
  invoice PDF → pdfplumber + regex structure + rule CoA
  bank PDF    → LocalPdfClient (via ProcessStatement elsewhere)
  image/audio → explicit error until Tesseract / faster-whisper sprints

Cloud mode (optional, paid/limited): OpenAI / LlamaParse / Groq.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.config import get_settings
from src.domain.exceptions import ExtractionError
from src.domain.models.bank_movement import BankMovement
from src.domain.models.enums import DocumentSource, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.classification.rule_coa import RuleCoAClassifier
from src.infrastructure.ocr.local_pdf_client import LocalPdfClient
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.transaction_repository import TransactionRepository

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm", ".ogg"}
_PDF_EXTENSION = ".pdf"
_TEXT_EXTENSIONS = {".txt"}
_AMOUNT_CANDIDATE = re.compile(
    r"(?:total|amount\s*due|balance\s*due|grand\s*total|invoice\s*total|amount)[^\d]{0,20}"
    r"\$?\s*(-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
    re.I,
)
_ANY_MONEY = re.compile(r"\$\s*(-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?|-?\d+\.\d{2})")
_DATE_ANY = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b"
)


class IngestDocumentUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository | None = None,
        movement_repo: BankMovementRepository | None = None,
        local_pdf: LocalPdfClient | None = None,
        coa: RuleCoAClassifier | None = None,
    ) -> None:
        self._transactions = transaction_repo or TransactionRepository()
        self._movements = movement_repo or BankMovementRepository()
        self._local_pdf = local_pdf or LocalPdfClient()
        self._coa = coa or RuleCoAClassifier()

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
        settings = get_settings()

        if ext in _IMAGE_EXTENSIONS:
            if settings.use_local_extraction:
                raise ExtractionError(
                    "Image OCR is free via Tesseract but not wired yet. "
                    "Sprint pendiente — meanwhile use PDF/Excel or EXTRACTION_MODE=cloud."
                )
            from src.infrastructure.llm.openai_client import OpenAIClient

            tx = await OpenAIClient().extract_from_image(file_path, tenant_id)
            return await self._transactions.save(tx)

        if ext in _AUDIO_EXTENSIONS:
            if settings.use_local_extraction:
                raise ExtractionError(
                    "Audio transcription is free via faster-whisper but not wired yet. "
                    "Sprint pendiente — or EXTRACTION_MODE=cloud with Groq free tier."
                )
            from src.infrastructure.llm.openai_client import OpenAIClient
            from src.infrastructure.llm.voice_client import VoiceClient

            tx = await VoiceClient(openai_client=OpenAIClient()).extract_from_audio(
                file_path, tenant_id
            )
            return await self._transactions.save(tx)

        if ext in _TEXT_EXTENSIONS:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            return await self._structure_local_text(
                text, file_path, tenant_id, DocumentSource.MANUAL
            )

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

    async def _ingest_invoice_pdf(
        self, file_path: Path, tenant_id: uuid.UUID
    ) -> FinancialTransaction:
        settings = get_settings()
        if settings.use_local_extraction:
            text = await self._local_pdf.extract_text_async(file_path)
            return await self._structure_local_text(
                text, file_path, tenant_id, DocumentSource.PDF
            )

        from src.infrastructure.llm.openai_client import OpenAIClient
        from src.infrastructure.ocr.llama_parse_client import LlamaParseClient

        text = await LlamaParseClient().extract_text(file_path)
        tx = await OpenAIClient().extract_from_text_document(
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
        settings = get_settings()
        if settings.use_local_extraction:
            movements = await self._local_pdf.parse_bank_statement_async(
                file_path, tenant_id, bank_name, bank_account_number, statement_month
            )
        else:
            from src.infrastructure.ocr.llama_parse_client import LlamaParseClient

            movements = await LlamaParseClient().parse_bank_statement(
                file_path, tenant_id, bank_name, bank_account_number, statement_month
            )
        saved: list[BankMovement] = []
        for movement in movements:
            match = self._coa.classify(tenant_id, movement.description)
            movement = movement.model_copy(
                update={
                    "chart_of_accounts_code": match.code,
                    "chart_of_accounts_name": match.name,
                    "category_confidence": match.confidence,
                }
            )
            saved.append(await self._movements.save(movement))
        return saved

    async def _structure_local_text(
        self,
        text: str,
        file_path: Path,
        tenant_id: uuid.UUID,
        source: DocumentSource,
    ) -> FinancialTransaction:
        amount = self._guess_amount(text)
        tx_date = self._guess_date(text)
        vendor = self._guess_vendor(text, file_path.name)
        description = (vendor or file_path.stem)[:512]
        match = self._coa.classify(tenant_id, f"{description} {text[:400]}")
        meta = ExtractionMetadata(
            source=source,
            raw_file_path=str(file_path),
            extraction_model="local_pdfplumber+rules",
            confidence_score=max(0.4, match.confidence * 0.9),
            raw_text=text[:8000],
        )
        tx = FinancialTransaction(
            tenant_id=tenant_id,
            transaction_date=tx_date,
            description=description,
            amount=amount,
            transaction_type=TransactionType.EXPENSE,
            chart_of_accounts_code=match.code,
            chart_of_accounts_name=match.name,
            category_confidence=match.confidence,
            ai_suggested_account_code=match.code,
            ai_suggested_account_name=match.name,
            vendor_name=vendor,
            metadata=meta,
        )
        return await self._transactions.save(tx)

    def _guess_amount(self, text: str) -> Decimal:
        for pattern in (_AMOUNT_CANDIDATE, _ANY_MONEY):
            matches = pattern.findall(text)
            if not matches:
                continue
            # Prefer last "total-like" or largest money found
            values: list[Decimal] = []
            for raw in matches:
                try:
                    values.append(Decimal(raw.replace(",", "").replace("$", "")))
                except InvalidOperation:
                    continue
            if values:
                return max(values, key=lambda v: abs(v)).copy_abs()
        return Decimal("0.01")

    def _guess_date(self, text: str) -> date:
        m = _DATE_ANY.search(text)
        if not m:
            return date.today()
        raw = m.group(1)
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return date.today()

    def _guess_vendor(self, text: str, filename: str) -> str:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        for ln in lines[:8]:
            if len(ln) < 3 or len(ln) > 80:
                continue
            if re.search(r"invoice|statement|page\s*\d|account", ln, re.I):
                continue
            if re.match(r"^[\d\W]+$", ln):
                continue
            return ln[:128]
        return Path(filename).stem[:128]
