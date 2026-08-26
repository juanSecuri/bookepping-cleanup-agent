"""
Parse bank/expense CSV or Excel (openpyxl) → FinancialTransaction list ($0).
"""
from __future__ import annotations

import csv
import logging
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.domain.exceptions import ExtractionError
from src.domain.models.enums import DocumentSource, TransactionStatus, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.classification.cash_flow import infer_cash_flow_type
from src.infrastructure.classification.rule_coa import RuleCoAClassifier
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.transaction_repository import TransactionRepository

logger = logging.getLogger(__name__)

_DATE_KEYS = ("date", "fecha", "transaction date", "posted", "value date", "fecha valor")
_DESC_KEYS = ("description", "desc", "memo", "concept", "concepto", "payee", "detalle", "narration")
_AMOUNT_KEYS = ("amount", "monto", "importe", "value", "valor")
_DEBIT_KEYS = ("debit", "débito", "debito", "withdrawal", "cargo", "outflow")
_CREDIT_KEYS = ("credit", "crédito", "credito", "deposit", "abono", "inflow")


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", (h or "").strip().lower())


def _find_col(headers: list[str], keys: tuple[str, ...]) -> int | None:
    for i, h in enumerate(headers):
        if h in keys or any(k in h for k in keys):
            return i
    return None


def _parse_amount(raw: object) -> Decimal | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "—"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace("€", "").replace(" ", "")
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        val = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    return -abs(val) if neg else val


def _parse_date(raw: object) -> date | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%m-%d-%Y", "%d-%m-%Y", "%m/%d/%y", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:10] if len(s) >= 10 and s[4] == "-" else s, fmt).date()
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            if a > 12:
                return date(y, b, a)
            return date(y, a, b)
        except ValueError:
            return None
    return None


class SpreadsheetIngestUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository | None = None,
        coa: RuleCoAClassifier | None = None,
    ) -> None:
        self._transactions = transaction_repo or TransactionRepository()
        self._coa = coa or RuleCoAClassifier()

    async def execute(self, file_path: Path, tenant_id: uuid.UUID) -> list[FinancialTransaction]:
        rows = self._load_rows(file_path)
        if not rows:
            raise ExtractionError(f"No tabular rows found in {file_path.name}")

        headers = [_norm_header(h) for h in rows[0]]
        date_i = _find_col(headers, _DATE_KEYS)
        desc_i = _find_col(headers, _DESC_KEYS)
        amt_i = _find_col(headers, _AMOUNT_KEYS)
        debit_i = _find_col(headers, _DEBIT_KEYS)
        credit_i = _find_col(headers, _CREDIT_KEYS)

        if date_i is None or desc_i is None:
            raise ExtractionError(
                f"Could not detect date/description columns in {file_path.name}. "
                f"Headers: {headers[:12]}"
            )
        if amt_i is None and debit_i is None and credit_i is None:
            raise ExtractionError(
                f"Could not detect amount/debit/credit columns in {file_path.name}."
            )

        coa_types = self._coa_types(str(tenant_id))
        saved: list[FinancialTransaction] = []
        for raw in rows[1:]:
            if not any(str(c).strip() for c in raw if c is not None):
                continue
            cells = list(raw) + [""] * max(0, len(headers) - len(raw))
            tx_date = _parse_date(cells[date_i])
            description = str(cells[desc_i] or "").strip()[:512]
            if not tx_date or len(description) < 2:
                continue

            debit = _parse_amount(cells[debit_i]) if debit_i is not None else None
            credit = _parse_amount(cells[credit_i]) if credit_i is not None else None
            amount_signed = _parse_amount(cells[amt_i]) if amt_i is not None else None

            if debit is not None and abs(debit) > 0 and (credit is None or credit == 0):
                amount, tx_type = abs(debit), TransactionType.EXPENSE
            elif credit is not None and abs(credit) > 0 and (debit is None or debit == 0):
                amount, tx_type = abs(credit), TransactionType.INCOME
            elif amount_signed is not None and amount_signed != 0:
                if amount_signed < 0:
                    amount, tx_type = abs(amount_signed), TransactionType.EXPENSE
                else:
                    amount, tx_type = amount_signed, TransactionType.INCOME
            else:
                continue

            match = self._coa.classify(tenant_id, description)
            acct_type = coa_types.get(match.code)
            cf = infer_cash_flow_type(account_code=match.code, account_type=acct_type)
            meta = ExtractionMetadata(
                source=DocumentSource.BANK_STATEMENT
                if file_path.suffix.lower() in {".csv", ".xlsx", ".xls"}
                else DocumentSource.MANUAL,
                raw_file_path=str(file_path),
                extraction_model="openpyxl+csv+rules_coa",
                confidence_score=float(match.confidence or 0.8),
                raw_text=description,
            )
            tx = FinancialTransaction(
                tenant_id=tenant_id,
                transaction_date=tx_date,
                description=description,
                amount=amount,
                transaction_type=tx_type,
                chart_of_accounts_code=match.code,
                chart_of_accounts_name=match.name,
                category_confidence=match.confidence,
                ai_suggested_account_code=match.code,
                ai_suggested_account_name=match.name,
                vendor_name=description.split("  ")[0][:128],
                cash_flow_type=cf,
                metadata=meta,
                status=TransactionStatus.PENDING_REVIEW,
            )
            saved.append(await self._transactions.save(tx))

        if not saved:
            raise ExtractionError(
                f"Parsed {file_path.name} but no valid movement rows. Check columns."
            )
        return saved

    def _load_rows(self, file_path: Path) -> list[list]:
        ext = file_path.suffix.lower()
        if ext == ".csv":
            text = file_path.read_text(encoding="utf-8-sig", errors="ignore")
            sample = text[:4096]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(text.splitlines(), dialect)
            return [list(r) for r in reader if any(str(c).strip() for c in r)]

        if ext in {".xlsx", ".xls"}:
            import openpyxl

            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            rows: list[list] = []
            for row in ws.iter_rows(values_only=True):
                rows.append(list(row))
            wb.close()
            return [r for r in rows if any(c is not None and str(c).strip() for c in r)]

        raise ExtractionError(f"Unsupported spreadsheet type: {ext}")

    def _coa_types(self, tenant_id: str) -> dict[str, str]:
        client = get_supabase_client()
        result = (
            client.table("chart_of_accounts")
            .select("code,account_type")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return {str(r["code"]): str(r["account_type"]) for r in (result.data or [])}
