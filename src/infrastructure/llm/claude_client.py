"""
Claude 3.5 Sonnet vision adapter.

Accepts a local file path (image) or raw bytes, encodes to base64,
and returns a fully validated FinancialTransaction domain entity via
Claude's structured output (tool_use forcing).
"""
from __future__ import annotations

import base64
import mimetypes
import uuid
from datetime import datetime
from pathlib import Path

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings
from src.domain.exceptions import ExtractionError
from src.domain.models.enums import DocumentSource
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction

_EXTRACTION_TOOL: dict = {
    "name": "extract_financial_transaction",
    "description": (
        "Extract all financial data from the provided receipt, invoice, or document image "
        "and return it as a structured JSON object."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "transaction_date", "description", "amount", "currency",
            "transaction_type", "vendor_name", "confidence_score",
        ],
        "properties": {
            "transaction_date": {
                "type": "string", "format": "date",
                "description": "Date of the transaction in YYYY-MM-DD format",
            },
            "description": {"type": "string", "maxLength": 512},
            "amount": {"type": "number", "exclusiveMinimum": 0},
            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
            "transaction_type": {
                "type": "string",
                "enum": ["income", "expense", "transfer", "journal_entry"],
            },
            "vendor_name": {"type": "string", "maxLength": 256},
            "tax_id": {"type": "string", "maxLength": 64},
            "invoice_number": {"type": "string", "maxLength": 128},
            "confidence_score": {
                "type": "number", "minimum": 0.0, "maximum": 1.0,
                "description": "Your confidence that the extracted data is correct",
            },
            "extra": {
                "type": "object",
                "description": "Any additional fields found in the document",
            },
        },
    },
}

_SYSTEM_PROMPT = """You are a forensic accountant and OCR specialist.
Your ONLY job is to extract financial data from the provided document image
and call the extract_financial_transaction tool with the data.
Rules:
- Never fabricate data. If a field is not visible, omit it.
- Amounts must always be positive numbers.
- Dates must be in YYYY-MM-DD format.
- Currency must be a 3-letter ISO 4217 code (default USD if not visible).
- Set confidence_score honestly: 0.95+ for perfectly legible, 0.5 for partially legible.
You MUST call the tool — do not return plain text."""


class ClaudeVisionClient:
    """
    Wraps the Anthropic Messages API to extract FinancialTransaction from images.

    Example:
        client = ClaudeVisionClient()
        tx = await client.extract_from_image(
            file_path=Path("receipts/2022-03.jpg"),
            tenant_id=uuid.UUID("..."),
        )
    """

    MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )

    def _encode_image(self, file_path: Path) -> tuple[str, str]:
        """Return (base64_data, media_type) for a local image file."""
        media_type, _ = mimetypes.guess_type(str(file_path))
        if media_type not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
            media_type = "image/jpeg"
        with open(file_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8"), media_type

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _call_api(self, image_b64: str, media_type: str) -> dict:
        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=[_EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "extract_financial_transaction"},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract all financial data from this document.",
                        },
                    ],
                }
            ],
        )
        # The model is forced to call the tool — find the tool_use block
        for block in response.content:
            if block.type == "tool_use" and block.name == "extract_financial_transaction":
                return block.input  # type: ignore[return-value]
        raise ExtractionError("Claude did not call the extraction tool as expected")

    async def extract_from_image(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        *,
        source: DocumentSource = DocumentSource.PHOTO,
    ) -> FinancialTransaction:
        """
        Extract a FinancialTransaction from a local image file.
        Returns a validated domain entity ready to be saved to Supabase.
        """
        if not file_path.exists():
            raise ExtractionError(f"File not found: {file_path}")

        image_b64, media_type = self._encode_image(file_path)

        try:
            data = self._call_api(image_b64, media_type)
        except anthropic.APIError as exc:
            raise ExtractionError(f"Anthropic API error: {exc}") from exc

        metadata = ExtractionMetadata(
            source=source,
            raw_file_path=str(file_path),
            extraction_model=self.MODEL,
            extraction_timestamp=datetime.utcnow(),
            confidence_score=float(data.get("confidence_score", 0.5)),
        )

        from decimal import Decimal
        return FinancialTransaction(
            tenant_id=tenant_id,
            transaction_date=data["transaction_date"],
            description=data["description"],
            amount=Decimal(str(data["amount"])),
            currency=data.get("currency", "USD"),
            transaction_type=data["transaction_type"],
            vendor_name=data.get("vendor_name"),
            tax_id=data.get("tax_id"),
            invoice_number=data.get("invoice_number"),
            metadata=metadata,
            extra=data.get("extra", {}),
        )
