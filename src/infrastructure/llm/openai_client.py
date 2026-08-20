"""
Unified OpenAI adapter — vision extraction, text structuring, and embeddings.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings
from src.domain.exceptions import ExtractionError
from src.domain.models.enums import DocumentSource
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.llm.extraction_schema import (
    EXTRACTION_PROPERTIES,
    EXTRACTION_REQUIRED,
    TEXT_SYSTEM_PROMPT,
    VISION_SYSTEM_PROMPT,
)

CHAT_MODEL = "gpt-4o"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
_TOOL_NAME = "extract_financial_transaction"

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": _TOOL_NAME,
        "description": "Extract structured financial transaction data from a document or transcript.",
        "parameters": {
            "type": "object",
            "properties": EXTRACTION_PROPERTIES,
            "required": EXTRACTION_REQUIRED,
        },
    },
}


class OpenAIClient:
    """Single OpenAI client for vision, text structuring, and embeddings."""

    def __init__(self, client: OpenAI | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            settings = get_settings()
            self._client = OpenAI(api_key=settings.openai_api_key.get_secret_value())

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6), reraise=True)
    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIM,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            input=texts,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIM,
        )
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    @staticmethod
    def _encode_image(file_path: Path) -> tuple[str, str]:
        media_type, _ = mimetypes.guess_type(str(file_path))
        if media_type not in _IMAGE_TYPES:
            media_type = "image/jpeg"
        data = base64.standard_b64encode(file_path.read_bytes()).decode("utf-8")
        return data, media_type

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
    def _call_tool(self, *, system: str, user_content: list | str) -> dict:
        response = self._client.chat.completions.create(
            model=CHAT_MODEL,
            max_tokens=1024,
            temperature=0.0,
            tools=[_EXTRACTION_TOOL],  # type: ignore[arg-type]
            tool_choice={"type": "function", "function": {"name": _TOOL_NAME}},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],  # type: ignore[arg-type]
        )
        message = response.choices[0].message
        if not message.tool_calls:
            raise ExtractionError("OpenAI did not call the extraction tool")
        raw_args = message.tool_calls[0].function.arguments
        return json.loads(raw_args)

    def _to_transaction(
        self,
        data: dict,
        *,
        tenant_id: uuid.UUID,
        metadata: ExtractionMetadata,
    ) -> FinancialTransaction:
        final_meta = metadata.model_copy(
            update={"confidence_score": float(data.get("confidence_score", 0.5))}
        )
        return FinancialTransaction(
            tenant_id=tenant_id,
            transaction_date=data["transaction_date"],
            description=data["description"],
            amount=Decimal(str(data["amount"])),
            currency=data.get("currency") or "USD",
            transaction_type=data["transaction_type"],
            vendor_name=data.get("vendor_name"),
            tax_id=data.get("tax_id"),
            invoice_number=data.get("invoice_number"),
            metadata=final_meta,
            extra=data.get("extra") or {},
        )

    async def extract_from_image(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        *,
        source: DocumentSource = DocumentSource.PHOTO,
    ) -> FinancialTransaction:
        if not file_path.exists():
            raise ExtractionError(f"File not found: {file_path}")

        image_b64, media_type = self._encode_image(file_path)
        try:
            data = self._call_tool(
                system=VISION_SYSTEM_PROMPT,
                user_content=[
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                    },
                    {"type": "text", "text": "Extract all financial data from this document."},
                ],
            )
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(f"OpenAI vision extraction failed: {exc}") from exc

        metadata = ExtractionMetadata(
            source=source,
            raw_file_path=str(file_path),
            extraction_model=CHAT_MODEL,
            extraction_timestamp=datetime.utcnow(),
            confidence_score=float(data.get("confidence_score", 0.5)),
        )
        return self._to_transaction(data, tenant_id=tenant_id, metadata=metadata)

    async def structure_text(
        self,
        text: str,
        tenant_id: uuid.UUID,
        metadata: ExtractionMetadata,
    ) -> FinancialTransaction:
        try:
            data = self._call_tool(system=TEXT_SYSTEM_PROMPT, user_content=text)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(f"OpenAI text structuring failed: {exc}") from exc
        return self._to_transaction(data, tenant_id=tenant_id, metadata=metadata)

    async def extract_from_text_document(
        self,
        text: str,
        file_path: Path,
        tenant_id: uuid.UUID,
        *,
        source: DocumentSource = DocumentSource.PDF,
    ) -> FinancialTransaction:
        metadata = ExtractionMetadata(
            source=source,
            raw_file_path=str(file_path),
            extraction_model=CHAT_MODEL,
            extraction_timestamp=datetime.utcnow(),
            confidence_score=0.7,
            raw_text=text[:4000],
        )
        return await self.structure_text(text, tenant_id, metadata)
