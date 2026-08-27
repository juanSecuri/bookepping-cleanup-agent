"""Tesseract OCR for invoice/receipt images and scanned PDF pages — $0 local path."""
from __future__ import annotations

import logging
from pathlib import Path

from src.domain.exceptions import ExtractionError

logger = logging.getLogger(__name__)

# Minimum chars from pdfplumber before we escalate to Tesseract on PDFs.
PDF_TEXT_MIN_CHARS = 80


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

    def extract_text_from_pdf(self, file_path: Path, *, lang: str = "eng+spa") -> str:
        """OCR each PDF page via pypdfium2 render → Tesseract (scanned statements)."""
        if not file_path.exists():
            raise ExtractionError(f"PDF not found: {file_path}")
        try:
            import pypdfium2 as pdfium
            import pytesseract
            from PIL import ImageOps
        except ImportError as exc:
            raise ExtractionError(f"OCR PDF deps missing: {exc}") from exc

        chunks: list[str] = []
        page_count = 0
        try:
            pdf = pdfium.PdfDocument(str(file_path))
            page_count = len(pdf)
            for page_index in range(page_count):
                page = pdf[page_index]
                try:
                    bitmap = page.render(scale=200 / 72)
                    pil = bitmap.to_pil()
                    gray = ImageOps.autocontrast(pil.convert("L"))
                    page_text = pytesseract.image_to_string(gray, lang=lang) or ""
                    page_text = page_text.strip()
                    if page_text:
                        chunks.append(page_text)
                except pytesseract.TesseractNotFoundError as exc:
                    raise ExtractionError(
                        "Tesseract binary missing. Deploy via Docker image with tesseract-ocr."
                    ) from exc
                except Exception as exc:
                    logger.warning(
                        "Tesseract page %s failed on %s: %s",
                        page_index + 1,
                        file_path.name,
                        exc,
                    )
            pdf.close()
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(f"Tesseract PDF OCR failed: {exc}") from exc

        text = "\n\n".join(chunks).strip()
        if not text:
            raise ExtractionError(
                f"Tesseract found no text in PDF {file_path.name} "
                f"({page_count} page(s), image-only or poor scan)."
            )
        logger.info(
            "Tesseract PDF OCR: %s chars from %s (%s/%s page(s))",
            len(text),
            file_path.name,
            len(chunks),
            page_count,
        )
        return text

    async def extract_text_async(self, file_path: Path, *, lang: str = "eng+spa") -> str:
        import asyncio

        return await asyncio.to_thread(self.extract_text, file_path, lang=lang)

    async def extract_text_from_pdf_async(
        self, file_path: Path, *, lang: str = "eng+spa"
    ) -> str:
        import asyncio

        return await asyncio.to_thread(self.extract_text_from_pdf, file_path, lang=lang)
