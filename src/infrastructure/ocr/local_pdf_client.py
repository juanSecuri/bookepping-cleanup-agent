"""
Free / local PDF extraction — no LlamaParse, no paid OCR APIs.

Uses pdfplumber (+ line heuristics) so bank statements and invoices
can be transcribed with open-source code only.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber

from src.domain.exceptions import ExtractionError
from src.domain.models.bank_movement import BankMovement

_AMOUNT_RE = re.compile(
    r"(?:\(?\$?\s*)(-?\d{1,3}(?:,\d{3})*(?:\.\d{2})?|-?\d+\.\d{2})(?:\s*\))?\s*$"
)
_DATE_LINE_RE = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\s+(.+)$"
)


def _parse_decimal(raw: str) -> Decimal:
    cleaned = raw.strip().replace(" ", "").replace("$", "").replace("€", "")
    neg = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")
    return -value if neg else value


def _normalise_date(raw: str, statement_month: str | None = None) -> date:
    raw = raw.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return date.fromisoformat(raw)

    year_hint = None
    if statement_month and re.match(r"^\d{4}-\d{2}$", statement_month):
        year_hint = int(statement_month[:4])

    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    m = re.match(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$", raw)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if y:
            year = int(y)
            if year < 100:
                year += 2000
        else:
            year = year_hint or date.today().year
        month, day = a, b
        if a > 12 and b <= 12:
            day, month = a, b
        try:
            return date(year, month, day)
        except ValueError:
            if a <= 12:
                return date(year, a, min(b, 28))
            raise
    raise ValueError(f"unparseable date: {raw}")


class LocalPdfClient:
    """$0 PDF text + bank-line extraction (company free-stack requirement)."""

    def extract_text(self, file_path: Path) -> str:
        if not file_path.exists():
            raise ExtractionError(f"PDF not found: {file_path}")
        chunks: list[str] = []
        try:
            with pdfplumber.open(str(file_path)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text.strip():
                        chunks.append(text)
                    for table in page.extract_tables() or []:
                        for row in table:
                            cells = [str(c).strip() if c else "" for c in row]
                            if any(cells):
                                chunks.append(" | ".join(cells))
        except Exception as exc:
            raise ExtractionError(f"Local PDF extract failed: {exc}") from exc
        text = "\n".join(chunks).strip()
        if not text:
            raise ExtractionError(f"No text extracted from {file_path.name} (local)")
        return text

    def parse_bank_statement(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
    ) -> list[BankMovement]:
        text = self.extract_text(file_path)
        movements = self._movements_from_text(
            text=text,
            tenant_id=tenant_id,
            bank_name=bank_name,
            bank_account_number=bank_account_number,
            statement_month=statement_month,
            source_file_path=str(file_path),
        )
        if not movements:
            raise ExtractionError(
                f"No movements extracted locally from {file_path.name}. "
                "PDF may be image-only (needs Tesseract sprint) or unfamiliar layout."
            )
        return movements

    async def parse_bank_statement_async(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
    ) -> list[BankMovement]:
        import asyncio

        return await asyncio.to_thread(
            self.parse_bank_statement,
            file_path,
            tenant_id,
            bank_name,
            bank_account_number,
            statement_month,
        )

    async def extract_text_async(self, file_path: Path) -> str:
        import asyncio

        return await asyncio.to_thread(self.extract_text, file_path)

    def _movements_from_text(
        self,
        *,
        text: str,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
        source_file_path: str,
    ) -> list[BankMovement]:
        movements: list[BankMovement] = []
        seen: set[tuple[str, str, str]] = set()

        for raw_line in text.splitlines():
            line = " ".join(raw_line.split())
            if len(line) < 8:
                continue
            upper = line.upper()
            if any(
                skip in upper
                for skip in (
                    "BEGINNING BALANCE",
                    "ENDING BALANCE",
                    "TOTAL FEES",
                    "PAGE ",
                    "ACCOUNT NUMBER",
                    "STATEMENT PERIOD",
                    "OPENING BALANCE",
                    "CLOSING BALANCE",
                )
            ):
                continue

            if "|" in line:
                cols = [c.strip() for c in line.split("|") if c.strip()]
                if len(cols) >= 3 and re.search(r"\d{1,2}[/-]\d{1,2}", cols[0]):
                    mov = self._row_to_movement(
                        cols,
                        tenant_id,
                        bank_name,
                        bank_account_number,
                        statement_month,
                        source_file_path,
                    )
                    if mov:
                        key = (
                            str(mov.movement_date),
                            mov.description[:80],
                            str(mov.debit_amount + mov.credit_amount),
                        )
                        if key not in seen:
                            seen.add(key)
                            movements.append(mov)
                    continue

            m = _DATE_LINE_RE.match(line)
            if not m:
                continue
            date_raw, rest = m.group(1), m.group(2)
            am = _AMOUNT_RE.search(rest)
            if not am:
                continue
            amount = abs(_parse_decimal(am.group(1)))
            if amount <= 0:
                continue
            description = rest[: am.start()].strip(" -|\t") or "Unknown"
            if len(description) < 2:
                continue
            try:
                movement_date = _normalise_date(date_raw, statement_month)
            except ValueError:
                continue

            desc_u = description.upper()
            is_payment = (
                "AUTOPAY" in desc_u
                or ("PAYMENT" in desc_u and "THANK" in desc_u)
                or desc_u.startswith("PAYMENT")
                or "DEPOSIT" in desc_u
            )
            if is_payment:
                debit, credit = Decimal("0"), amount
            else:
                debit, credit = amount, Decimal("0")

            key = (str(movement_date), description[:80], str(amount))
            if key in seen:
                continue
            seen.add(key)
            movements.append(
                BankMovement(
                    tenant_id=tenant_id,
                    bank_account_number=bank_account_number,
                    bank_name=bank_name,
                    movement_date=movement_date,
                    description=description[:512],
                    debit_amount=debit,
                    credit_amount=credit,
                    source_file_path=source_file_path,
                    statement_month=statement_month,
                )
            )

        return movements

    def _row_to_movement(
        self,
        cols: list[str],
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
        source_file_path: str,
    ) -> BankMovement | None:
        date_raw = cols[0]
        description = cols[1] if len(cols) > 1 else "Unknown"
        debit = Decimal("0")
        credit = Decimal("0")
        if len(cols) >= 4:
            debit = abs(_parse_decimal(cols[2])) if cols[2] else Decimal("0")
            credit = abs(_parse_decimal(cols[3])) if cols[3] else Decimal("0")
        elif len(cols) == 3:
            amt = abs(_parse_decimal(cols[2]))
            debit, credit = amt, Decimal("0")
        if debit == 0 and credit == 0:
            return None
        try:
            movement_date = _normalise_date(date_raw, statement_month)
        except ValueError:
            return None
        return BankMovement(
            tenant_id=tenant_id,
            bank_account_number=bank_account_number,
            bank_name=bank_name,
            movement_date=movement_date,
            description=description[:512],
            debit_amount=debit,
            credit_amount=credit,
            source_file_path=source_file_path,
            statement_month=statement_month,
        )
