"""Heuristics to classify Drive files (bank statement vs invoice vs spreadsheet).

Supports nested layouts like IMG 1–3:
  Client / Bank folder / [account ####] / [year YYYY] / statement.pdf
  Client / Bank … #### / [year] / statement.pdf
"""
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

BANK_NAME_MAP = (
    ("wells fargo", "Wells Fargo"),
    ("wellsfargo", "Wells Fargo"),
    ("chase", "Chase"),
    ("truist", "Truist"),
    ("citi", "Citi"),
    ("costco", "Citi Costco"),
    ("best buy", "Citi Best Buy"),
    ("elan", "Elan"),
    ("jetstream", "Jetstream"),
    ("dade county", "Dade County FCU"),
)

STATEMENT_NAME_RE = re.compile(
    r"(statement|wellsfargo|wells.?fargo|chase|truist|citi|^\d{6}\b|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    re.I,
)

ACCOUNT_IN_NAME_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")
YEAR_FOLDER_RE = re.compile(r"^20\d{2}$")
ACCOUNT_FOLDER_RE = re.compile(r"^\d{4}$")


@dataclass
class DriveFilePlan:
    kind: str  # statement | invoice | spreadsheet | skip
    bank_name: str | None = None
    bank_account_number: str | None = None
    statement_month: str | None = None
    fiscal_year: str | None = None
    folder_group: str | None = None  # UI label: Bank / #### / YYYY
    note: str | None = None


def _path_parts(path: str, name: str) -> list[str]:
    full = f"{path}/{name}" if path and not path.endswith(name) else (path or name)
    return [p for p in full.replace("\\", "/").split("/") if p]


def _detect_bank(parts: list[str]) -> str:
    for p in parts:
        pl = p.lower()
        for key, label in BANK_NAME_MAP:
            if key in pl:
                return label
    joined = " / ".join(parts).lower()
    for key, label in BANK_NAME_MAP:
        if key in joined:
            return label
    return "Bank"


def _detect_account(parts: list[str], bank_name: str) -> str:
    """Prefer dedicated #### folder; else last 4 digits in bank folder name."""
    # Nested account folders (Wells Fargo … / 8398 / 2025)
    for p in parts:
        if ACCOUNT_FOLDER_RE.fullmatch(p) and not YEAR_FOLDER_RE.fullmatch(p):
            # Prefer folders that are siblings under a bank folder (not years)
            return p
    # Account embedded in folder name: "Truist Checking 4461", "Chase Credit Card 5841"
    for p in reversed(parts):
        if YEAR_FOLDER_RE.fullmatch(p):
            continue
        if ACCOUNT_FOLDER_RE.fullmatch(p):
            continue
        m = ACCOUNT_IN_NAME_RE.search(p)
        if m:
            return m.group(1)
    return "0000"


def _detect_year_and_month(parts: list[str], name: str) -> tuple[str | None, str | None]:
    year: str | None = None
    month: str | None = None
    for p in parts:
        if YEAR_FOLDER_RE.fullmatch(p):
            year = p
            break

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
        year = m2.group(2)
        month = f"{year}-{months.get(key, '01')}"
    else:
        m = re.match(r"^(\d{2})(\d{2})(\d{2})", name)
        if m:
            # MMDDYY
            year = f"20{m.group(3)}"
            month = f"{year}-{m.group(1)}"
        elif year:
            month = f"{year}-01"

    if not month:
        from datetime import date

        month = date.today().strftime("%Y-%m")
        year = year or month[:4]

    return year, month


def classify_drive_file(name: str, path: str = "", mime_type: str = "") -> DriveFilePlan:
    lower_name = name.lower()
    parts = _path_parts(path, name)
    # Drop the filename from structural parts
    struct = parts[:-1] if parts and parts[-1] == name else parts
    joined = " / ".join(parts).lower()

    if lower_name.endswith((".xlsx", ".xls", ".csv")) or "spreadsheet" in (mime_type or ""):
        bank = _detect_bank(struct)
        acct = _detect_account(struct, bank)
        year, _ = _detect_year_and_month(struct, name)
        group = " / ".join(p for p in [bank, acct if acct != "0000" else None, year] if p)
        return DriveFilePlan(
            kind="spreadsheet",
            bank_name=bank,
            bank_account_number=acct,
            fiscal_year=year,
            folder_group=group or "Spreadsheets",
            note="Excel/CSV: se registra; extracción tabular vía openpyxl.",
        )

    if not (lower_name.endswith(".pdf") or "pdf" in (mime_type or "")):
        if lower_name.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return DriveFilePlan(kind="invoice", folder_group="Imágenes", note="Imagen -> factura/recibo")
        return DriveFilePlan(kind="skip", note="Tipo no soportado para ingest automático")

    looks_bank = any(k in joined for k in BANK_KEYWORDS) or bool(STATEMENT_NAME_RE.search(name))
    if looks_bank:
        bank_name = _detect_bank(struct)
        account = _detect_account(struct, bank_name)
        year, month = _detect_year_and_month(struct, name)
        group_parts = [bank_name]
        if account and account != "0000":
            group_parts.append(account)
        if year:
            group_parts.append(year)
        folder_group = " / ".join(group_parts)

        return DriveFilePlan(
            kind="statement",
            bank_name=bank_name,
            bank_account_number=account,
            statement_month=month,
            fiscal_year=year,
            folder_group=folder_group,
            note=f"Estado de cuenta → {folder_group} ({month})",
        )

    return DriveFilePlan(kind="invoice", folder_group="Facturas", note="PDF -> factura/recibo (ingesta)")
