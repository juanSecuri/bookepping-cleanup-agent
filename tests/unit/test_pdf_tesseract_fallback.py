"""Unit tests for pdfplumber → Tesseract fallback (no system tesseract required)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.domain.exceptions import ExtractionError
from src.infrastructure.ocr.extraction_result import apis_used_for_engine
from src.infrastructure.ocr.local_pdf_client import LocalPdfClient
from src.infrastructure.ocr.tesseract_client import PDF_TEXT_MIN_CHARS


def test_needs_tesseract_fallback_empty() -> None:
    assert LocalPdfClient._needs_tesseract_fallback("", 3) is True


def test_needs_tesseract_fallback_short_text() -> None:
    assert LocalPdfClient._needs_tesseract_fallback("abc", 1) is True


def test_needs_tesseract_fallback_good_text() -> None:
    text = "A" * (PDF_TEXT_MIN_CHARS + 10) + " invoice total $100.00"
    assert LocalPdfClient._needs_tesseract_fallback(text, 1) is False


def test_apis_used_for_engine() -> None:
    assert "tesseract" in apis_used_for_engine("tesseract").lower()
    assert "pdfplumber" in apis_used_for_engine("pdfplumber").lower()


def test_extract_text_with_engine_escalates_to_tesseract(tmp_path: Path) -> None:
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    mock_ocr = MagicMock()
    mock_ocr.extract_text_from_pdf.return_value = "01/15/2024 Grocery Store 45.00"

    client = LocalPdfClient(ocr=mock_ocr)
    with patch.object(client, "_extract_pdfplumber_text", return_value=("", 2)):
        result = client.extract_text_with_engine(pdf)

    assert result.engine == "tesseract"
    assert "Grocery" in result.text
    mock_ocr.extract_text_from_pdf.assert_called_once_with(pdf)


def test_extract_text_with_engine_keeps_pdfplumber_when_rich(tmp_path: Path) -> None:
    pdf = tmp_path / "digital.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    rich = "x" * (PDF_TEXT_MIN_CHARS + 50) + " 01/01/2024 Payment 10.00"

    mock_ocr = MagicMock()
    client = LocalPdfClient(ocr=mock_ocr)
    with patch.object(client, "_extract_pdfplumber_text", return_value=(rich, 1)):
        result = client.extract_text_with_engine(pdf)

    assert result.engine == "pdfplumber"
    assert result.text == rich
    mock_ocr.extract_text_from_pdf.assert_not_called()


def test_extract_text_raises_when_both_fail(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    mock_ocr = MagicMock()
    mock_ocr.extract_text_from_pdf.side_effect = ExtractionError("no ocr text")

    client = LocalPdfClient(ocr=mock_ocr)
    with patch.object(client, "_extract_pdfplumber_text", return_value=("", 1)):
        with pytest.raises(ExtractionError, match="pdfplumber \\+ Tesseract"):
            client.extract_text_with_engine(pdf)


def test_parse_bank_statement_retries_tesseract_when_no_movements(tmp_path: Path) -> None:
    from uuid import uuid4

    pdf = tmp_path / "stmt.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    tenant = uuid4()

    mock_ocr = MagicMock()
    mock_ocr.extract_text_from_pdf.return_value = "01/15/2024 OFFICE SUPPLY 45.67\n"
    client = LocalPdfClient(ocr=mock_ocr)

    plumber_text = "HEADER ONLY NO MOVEMENT LINES HERE BUT LONG ENOUGH " * 3
    with patch.object(client, "_extract_pdfplumber_text", return_value=(plumber_text, 1)):
        movements = client.parse_bank_statement(pdf, tenant, "Citi", "1234", "2024-01")

    assert len(movements) == 1
    assert movements[0].description.startswith("OFFICE")
    assert client.last_extraction_engine == "tesseract"
