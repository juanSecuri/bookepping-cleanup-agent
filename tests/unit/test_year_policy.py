"""Unit tests for per-workspace fiscal-year cutoff helpers."""
from __future__ import annotations

from src.infrastructure.drive.year_policy import (
    is_beyond_max_year,
    parse_max_fiscal_year,
    year_from_drive_path,
)


def test_parse_max_fiscal_year() -> None:
    assert parse_max_fiscal_year(None) is None
    assert parse_max_fiscal_year("") is None
    assert parse_max_fiscal_year(2025) == 2025
    assert parse_max_fiscal_year("2025") == 2025
    assert parse_max_fiscal_year(1999) is None


def test_year_from_drive_path_prefers_folder() -> None:
    path = "TPC Clients/My Xcell Network CORP/Wells Fargo/8398/2026"
    assert year_from_drive_path(path, "statement.pdf") == 2026
    assert year_from_drive_path(path.replace("2026", "2025"), "jan.pdf") == 2025


def test_no_ceiling_never_blocks() -> None:
    assert not is_beyond_max_year(
        "…/2026/stmt.pdf",
        "stmt.pdf",
        fiscal_year="2026",
        max_year=None,
    )


def test_workspace_ceiling_blocks_later_years_only() -> None:
    assert is_beyond_max_year(
        "…/2026/stmt.pdf",
        "stmt.pdf",
        fiscal_year="2026",
        max_year=2025,
    )
    assert not is_beyond_max_year(
        "…/2025/stmt.pdf",
        "stmt.pdf",
        fiscal_year="2025",
        max_year=2025,
    )
    assert not is_beyond_max_year(
        "…/2024/stmt.pdf",
        "stmt.pdf",
        fiscal_year="2024",
        max_year=2025,
    )
