"""Smoke tests for OCR / voice helpers (no system tesseract required)."""
from src.infrastructure.classification.cash_flow import infer_cash_flow_type
from src.infrastructure.llm.local_voice import LocalVoiceTranscriber
from src.infrastructure.ocr.tesseract_client import PDF_TEXT_MIN_CHARS, TesseractOcrClient


def test_voice_supported_extensions() -> None:
    from src.infrastructure.llm import local_voice as lv

    assert ".mp3" in lv._SUPPORTED
    assert ".wav" in lv._SUPPORTED


def test_transcriber_constructs() -> None:
    assert LocalVoiceTranscriber() is not None


def test_cash_flow_still_ok() -> None:
    assert infer_cash_flow_type(account_code="3030") == "financing"


def test_tesseract_pdf_min_chars_threshold() -> None:
    assert PDF_TEXT_MIN_CHARS >= 40


def test_tesseract_client_constructs() -> None:
    assert TesseractOcrClient() is not None
