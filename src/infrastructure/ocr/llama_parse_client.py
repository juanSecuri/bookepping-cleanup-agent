"""
LlamaParse adapter for complex bank statement PDF extraction.

LlamaParse reconstructs the tabular structure of bank statement PDFs
row-by-row, preserving debit/credit columns even in multi-column layouts.

Workflow:
  1. Upload PDF → LlamaParse processes asynchronously.
  2. Poll for result → get structured markdown tables.
  3. Parse each table row into a BankMovement domain entity.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from llama_parse import LlamaParse
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings
from src.domain.exceptions import ExtractionError
from src.domain.models.bank_movement import BankMovement

_DATE_PATTERNS = [
    r"\d{2}/\d{2}/\d{4}",   # DD/MM/YYYY
    r"\d{4}-\d{2}-\d{2}",   # YYYY-MM-DD
    r"\d{2}-\d{2}-\d{4}",   # DD-MM-YYYY
]


def _parse_decimal(raw: str) -> Decimal:
    """Convert formatted number strings like '1.234,56' or '1,234.56' to Decimal."""
    cleaned = raw.strip().replace(" ", "").replace("$", "").replace("€", "")
    # European format: 1.234,56 → 1234.56
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def _normalise_date(raw: str) -> str:
    """Return date in YYYY-MM-DD regardless of input format."""
    raw = raw.strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            from datetime import datetime as dt
            return dt.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw   # Return as-is if format not recognized


class LlamaParseClient:
    """
    Extracts BankMovement entities from bank statement PDFs.

    Example:
        client = LlamaParseClient()
        movements = await client.parse_bank_statement(
            file_path=Path("statements/2022-06-bancolombia.pdf"),
            tenant_id=uuid.UUID("..."),
            bank_name="Bancolombia",
            bank_account_number="123-456789",
            statement_month="2022-06",
        )
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._parser = LlamaParse(
            api_key=settings.llamaparse_api_key.get_secret_value(),
            result_type="markdown",
            verbose=False,
            language="es",
            parsing_instruction=(
                "This is a bank statement. Extract every transaction row as a markdown table "
                "with columns: Date | Description | Reference | Debit | Credit | Balance. "
                "Preserve all rows. Do not summarize."
            ),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15), reraise=True)
    def _parse_pdf(self, file_path: Path) -> str:
        """Upload PDF and return full markdown string."""
        documents = self._parser.load_data(str(file_path))
        return "\n\n".join(doc.text for doc in documents)

    def _parse_markdown_tables(
        self,
        markdown: str,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
        source_file_path: str,
    ) -> list[BankMovement]:
        """Parse markdown tables into BankMovement entities."""
        movements: list[BankMovement] = []
        in_table = False
        header_seen = False

        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                cols = [c.strip() for c in stripped.strip("|").split("|")]
                if not header_seen:
                    header_seen = True
                    in_table = True
                    continue
                if set(stripped.replace("|", "").replace("-", "").replace(" ", "")) == set():
                    continue   # separator row
                if len(cols) < 4:
                    continue

                date_raw = cols[0] if cols else ""
                description = cols[1] if len(cols) > 1 else "Unknown"
                reference = cols[2] if len(cols) > 2 else None
                debit_raw = cols[3] if len(cols) > 3 else "0"
                credit_raw = cols[4] if len(cols) > 4 else "0"
                balance_raw = cols[5] if len(cols) > 5 else None

                if not re.search(r"\d", date_raw):
                    continue  # Skip non-data rows

                debit = _parse_decimal(debit_raw) if debit_raw else Decimal("0")
                credit = _parse_decimal(credit_raw) if credit_raw else Decimal("0")

                if debit == Decimal("0") and credit == Decimal("0"):
                    continue

                try:
                    movement = BankMovement(
                        tenant_id=tenant_id,
                        bank_account_number=bank_account_number,
                        bank_name=bank_name,
                        movement_date=_normalise_date(date_raw),
                        description=description[:512],
                        reference=reference[:256] if reference else None,
                        debit_amount=debit,
                        credit_amount=credit,
                        running_balance=_parse_decimal(balance_raw) if balance_raw else None,
                        source_file_path=source_file_path,
                        statement_month=statement_month,
                    )
                    movements.append(movement)
                except Exception:
                    continue   # Skip malformed rows — log in production
            else:
                if in_table:
                    header_seen = False
                    in_table = False

        return movements

    async def extract_text(self, file_path: Path) -> str:
        """Extract raw markdown/text from any PDF (invoices, receipts, etc.)."""
        if not file_path.exists():
            raise ExtractionError(f"PDF not found: {file_path}")
        try:
            text = self._parse_pdf(file_path)
        except Exception as exc:
            raise ExtractionError(f"LlamaParse failed: {exc}") from exc
        if not text.strip():
            raise ExtractionError(f"No text extracted from {file_path.name}")
        return text

    async def parse_bank_statement(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
    ) -> list[BankMovement]:
        """Parse a bank statement PDF and return list of BankMovement entities."""
        markdown = await self.extract_text(file_path)

        movements = self._parse_markdown_tables(
            markdown=markdown,
            tenant_id=tenant_id,
            bank_name=bank_name,
            bank_account_number=bank_account_number,
            statement_month=statement_month,
            source_file_path=str(file_path),
        )

        if not movements:
            raise ExtractionError(
                f"No movements extracted from {file_path.name}. "
                "Check that LlamaParse could read the table structure."
            )

        return movements
