"""Tesseract OCR for invoice/receipt images — $0 local path."""
from __future__ import annotations

import logging
from pathlib import Path

from src.domain.exceptions import ExtractionError

logger = logging.getLogger(__name__)


class TesseractOcrClient:
    """Pillow + pytesseract. Requires tesseract-ocr binary on PATH (Docker image)."""

    def extract_text(self, file_path: Path, *, lang: str = "eng+spa") -> str:
        if not file_path.exists():
            raise ExtractionError(f"Image not found: {file_path}")
        try:
            import pytesseract
            from PIL import Image, ImageOps
        except ImportError as exc:
            raise ExtractionError(
                "pytesseract/Pillow not installed. Rebuild with OCR deps."
            ) from exc

        try:
            img = Image.open(file_path)
            img = ImageOps.exif_transpose(img)
            # Light preprocess: grayscale + autocontrast helps receipts
            gray = ImageOps.autocontrast(img.convert("L"))
            text = pytesseract.image_to_string(gray, lang=lang) or ""
            text = text.strip()
        except pytesseract.TesseractNotFoundError as exc:
            raise ExtractionError(
                "Tesseract binary missing. Deploy via Docker image with tesseract-ocr."
            ) from exc
        except Exception as exc:
            raise ExtractionError(f"Tesseract OCR failed: {exc}") from exc

        if not text:
            raise ExtractionError(
                f"No text from OCR on {file_path.name}. Try a clearer photo or PDF."
            )
        logger.info("Tesseract extracted %s chars from %s", len(text), file_path.name)
        return text

    async def extract_text_async(self, file_path: Path, *, lang: str = "eng+spa") -> str:
        import asyncio

        return await asyncio.to_thread(self.extract_text, file_path, lang=lang)
