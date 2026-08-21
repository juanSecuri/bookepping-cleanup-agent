"""Heuristics to classify Drive files (bank statement vs invoice vs spreadsheet)."""
from __future__ import annotations

import re
from dataclasses import dataclass


BANK_KEYWORDS = (
    "wells fargo",
    "wellsfargo",
    "chase",
    "truist",
    "citi",
    "costco",
    "best buy",
    "elan",
    "jetstream",
    "credit card",
    "checking",
    "dade county",
    "federal credit",
)

STATEMENT_NAME_RE = re.compile(
    r"(statement|wellsfargo|wells.?fargo|chase|truist|citi|^\d{6}\b|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    re.I,
)


@dataclass
class DriveFilePlan:
    kind: str  # statement | invoice | spreadsheet | skip
    bank_name: str | None = None
    bank_account_number: str | None = None
    statement_month: str | None = None
    note: str | None = None


def _path_parts(path: str, name: str) -> list[str]:
    full = f"{path}/{name}" if path and not path.endswith(name) else (path or name)
    return [p for p in full.replace("\\", "/").split("/") if p]


def classify_drive_file(name: str, path: str = "", mime_type: str = "") -> DriveFilePlan:
    lower_name = name.lower()
    parts = _path_parts(path, name)
    joined = " / ".join(parts).lower()

    # Spreadsheets
    if lower_name.endswith((".xlsx", ".xls", ".csv")) or "spreadsheet" in (mime_type or ""):
        return DriveFilePlan(
            kind="spreadsheet",
            note="Excel/CSV: se registra; extracción tabular completa llega en siguiente iteración.",
        )

    if not (lower_name.endswith(".pdf") or "pdf" in (mime_type or "")):
        if lower_name.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return DriveFilePlan(kind="invoice", note="Imagen -> factura/recibo")
        return DriveFilePlan(kind="skip", note="Tipo no soportado para ingest automático")

    looks_bank = any(k in joined for k in BANK_KEYWORDS) or bool(STATEMENT_NAME_RE.search(name))
    if looks_bank:
        bank_name = "Bank"
        account = "0000"
        month = None
        for p in parts:
            pl = p.lower()
            if "wells" in pl:
                bank_name = "Wells Fargo"
            elif "chase" in pl:
                bank_name = "Chase"
            elif "truist" in pl:
                bank_name = "Truist"
            elif "citi" in pl or "costco" in pl or "best buy" in pl:
                bank_name = p
            elif "elan" in pl:
                bank_name = "Elan"
            elif "jetstream" in pl:
                bank_name = "Jetstream"
            if re.fullmatch(r"20\d{2}", p):
                # year folder — month from filename if possible
                year = p
                m = re.match(r"^(\d{2})(\d{2})(\d{2})", name)
                if m:
                    # MMDDYY e.g. 052226
                    month = f"20{m.group(3)}-{m.group(1)}"
                else:
                    month = f"{year}-01"
            elif re.fullmatch(r"\d{4}", p):
                account = p
            # "May 2026.pdf"
            m2 = re.search(
                r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{4})",
                name,
                re.I,
            )
            if m2:
                months = {
                    "jan": "01",
                    "feb": "02",
                    "mar": "03",
                    "apr": "04",
                    "may": "05",
                    "jun": "06",
                    "jul": "07",
                    "aug": "08",
                    "sep": "09",
                    "oct": "10",
                    "nov": "11",
                    "dec": "12",
                }
                key = m2.group(1).lower()[:3]
                month = f"{m2.group(2)}-{months.get(key, '01')}"

        if not month:
            m = re.match(r"^(\d{2})(\d{2})(\d{2})", name)
            if m:
                month = f"20{m.group(3)}-{m.group(1)}"
            else:
                from datetime import date

                month = date.today().strftime("%Y-%m")

        return DriveFilePlan(
            kind="statement",
            bank_name=bank_name,
            bank_account_number=account,
            statement_month=month,
            note=f"Estado de cuenta -> movimientos ({bank_name} ...{account} {month})",
        )

    return DriveFilePlan(kind="invoice", note="PDF -> factura/recibo (ingesta)")
