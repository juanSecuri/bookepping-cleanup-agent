"""Shared PDF/image extraction result + apis_used labels."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PdfExtractionResult:
    text: str
    engine: str  # "pdfplumber" | "tesseract"

    @property
    def apis_used(self) -> str:
        return apis_used_for_engine(self.engine)


def apis_used_for_engine(engine: str) -> str:
    if engine == "tesseract":
        return "pdfplumber + Tesseract OCR (local $0), reglas CoA"
    if engine == "llamaparse":
        return "LlamaParse (cloud), reglas CoA"
    return "pdfplumber (local $0), reglas CoA"
