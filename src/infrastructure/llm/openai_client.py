"""
OpenAI adapter — embeddings generation and cross-analysis utilities.

Primary uses:
  1. Generate embeddings for Chart-of-Accounts entries (used by VectorRepository).
  2. Cross-validate ambiguous extractions (e.g. confirm vendor from multiple documents).
  3. Batch-classify large transaction lists when Claude quotas are tight.
"""
from __future__ import annotations

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_settings

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
CHAT_MODEL = "gpt-4o-mini"


class OpenAIClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = OpenAI(api_key=settings.openai_api_key.get_secret_value())

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6), reraise=True)
    def embed(self, text: str) -> list[float]:
        """Return a 1536-dim embedding vector for the given text."""
        response = self._client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIM,
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in one API call (max 2048 inputs per call)."""
        response = self._client.embeddings.create(
            input=texts,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIM,
        )
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=6), reraise=True)
    def cross_validate(self, context: str, question: str) -> str:
        """
        Ask GPT-4o-mini a yes/no or short-answer question about accounting context.
        Used for disambiguation when Claude extraction confidence is below 0.70.
        """
        response = self._client.chat.completions.create(
            model=CHAT_MODEL,
            max_tokens=256,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a forensic accountant. Answer concisely and only based "
                        "on the provided context. If unsure, say 'uncertain'."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                },
            ],
        )
        return response.choices[0].message.content or ""
