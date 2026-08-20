"""
TextStructurer — converts a plain-text transcript (voice or OCR)
into a validated FinancialTransaction using Claude (text-only mode).

This is the shared 'second stage' for:
  - Voice notes after Groq transcription
  - Any text snippet pasted manually
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings
from src.domain.exceptions import ExtractionError
from src.domain.models.enums import DocumentSource
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction

_TOOL_SCHEMA: dict = {
    "name": "structure_transaction",
    "description": "Parse a free-text financial description into structured transaction data.",
    "input_schema": {
        "type": "object",
        "required": ["transaction_date", "description", "amount", "transaction_type", "confidence_score"],
        "properties": {
            "transaction_date": {"type": "string", "format": "date"},
            "description": {"type": "string"},
            "amount": {"type": "number", "exclusiveMinimum": 0},
            "currency": {"type": "string", "minLength": 3, "maxLength": 3},
            "transaction_type": {"type": "string", "enum": ["income", "expense", "transfer", "journal_entry"]},
            "vendor_name": {"type": "string"},
            "tax_id": {"type": "string"},
            "invoice_number": {"type": "string"},
            "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
    },
}

_SYSTEM = """You are an expert bookkeeper. Given a free-text description of a financial event
(possibly a voice-note transcript or OCR output), call the structure_transaction tool with
the structured data. Always extract the date, amount, and type. Use USD if currency is unknown."""


class TextStructurer:
    MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6), reraise=True)
    def _call(self, text: str) -> dict:
        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=512,
            system=_SYSTEM,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "structure_transaction"},
            messages=[{"role": "user", "content": text}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "structure_transaction":
                return block.input  # type: ignore[return-value]
        raise ExtractionError("Claude did not return structured data")

    async def structure_transcript(
        self,
        transcript: str,
        tenant_id: uuid.UUID,
        metadata: ExtractionMetadata,
    ) -> FinancialTransaction:
        try:
            data = self._call(transcript)
        except anthropic.APIError as exc:
            raise ExtractionError(f"Claude API error during text structuring: {exc}") from exc

        # Rebuild metadata with updated confidence from model output
        final_metadata = metadata.model_copy(
            update={"confidence_score": float(data.get("confidence_score", 0.7))}
        )

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
            metadata=final_metadata,
        )
