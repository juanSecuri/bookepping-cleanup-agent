"""Per-workspace fiscal-year cutoff for Drive ingest and cleanup.

NULL / unset on a workspace = no year filter (other clients stay unrestricted).
My Xcell Network is configured with max_fiscal_year=2025 for CPA taxes.
"""
from __future__ import annotations

import re

YEAR_FOLDER_RE = re.compile(r"(?:^|/)(20\d{2})(?:/|$)")
YEAR_TOKEN_RE = re.compile(r"\b(20\d{2})\b")


def parse_max_fiscal_year(value: object | None) -> int | None:
    """Normalize workspace / request value → int year or None (no cutoff)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 2000 <= value <= 2100 else None
    text = str(value).strip()
    if not text:
        return None
    try:
        year = int(text[:4])
    except ValueError:
        return None
    return year if 2000 <= year <= 2100 else None


def year_from_drive_path(path: str | None, name: str | None = None) -> int | None:
    """Prefer dedicated YYYY folder in the Drive path; else year token in path/name."""
    hay = f"{path or ''}/{name or ''}".replace("\\", "/")
    for part in hay.split("/"):
        if re.fullmatch(r"20\d{2}", part.strip()):
            return int(part.strip())
    m = YEAR_FOLDER_RE.search(hay)
    if m:
        return int(m.group(1))
    m2 = YEAR_TOKEN_RE.search(hay)
    if m2:
        return int(m2.group(1))
    return None


def is_beyond_max_year(
    path: str | None,
    name: str | None = None,
    *,
    fiscal_year: str | int | None = None,
    max_year: int | None = None,
) -> bool:
    """True when file year > workspace ceiling. False if no ceiling is set."""
    ceiling = parse_max_fiscal_year(max_year)
    if ceiling is None:
        return False
    year: int | None = None
    if fiscal_year is not None and str(fiscal_year).strip():
        try:
            year = int(str(fiscal_year).strip()[:4])
        except ValueError:
            year = None
    if year is None:
        year = year_from_drive_path(path, name)
    if year is None:
        return False
    return year > ceiling
