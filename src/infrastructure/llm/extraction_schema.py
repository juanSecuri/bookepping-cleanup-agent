"""Shared JSON schema + prompts for OpenAI transaction extraction."""
from __future__ import annotations

EXTRACTION_PROPERTIES: dict = {
    "transaction_date": {
        "type": "string",
        "description": "Transaction date in YYYY-MM-DD format",
    },
    "description": {"type": "string", "description": "Short description, max 512 chars"},
    "amount": {"type": "number", "description": "Positive amount only"},
    "currency": {
        "type": "string",
        "description": "ISO 4217 currency code, default USD",
    },
    "transaction_type": {
        "type": "string",
        "enum": ["income", "expense", "transfer", "journal_entry"],
    },
    "vendor_name": {"type": "string"},
    "tax_id": {"type": "string"},
    "invoice_number": {"type": "string"},
    "confidence_score": {
        "type": "number",
        "description": "Confidence 0.0–1.0 that extracted data is correct",
    },
    "extra": {
        "type": "object",
        "description": "Any additional fields found in the document",
    },
}

EXTRACTION_REQUIRED = [
    "transaction_date",
    "description",
    "amount",
    "currency",
    "transaction_type",
    "vendor_name",
    "confidence_score",
]

VISION_SYSTEM_PROMPT = """You are a forensic accountant and OCR specialist.
Extract financial data from the document and return structured JSON only.
Rules:
- Never fabricate data. If a field is not visible, omit optional fields.
- Amounts must always be positive numbers.
- Dates must be YYYY-MM-DD.
- Currency must be a 3-letter ISO 4217 code (default USD).
- confidence_score: 0.95+ if perfectly legible, ~0.5 if partially legible."""

TEXT_SYSTEM_PROMPT = """You are an expert bookkeeper.
Given a free-text description of a financial event (voice transcript or OCR),
return structured JSON. Always extract date, amount, and type.
Use USD if currency is unknown. Never invent amounts or dates."""
