"""
pgvector-backed repository for Chart-of-Accounts semantic search (RAG engine).

Expected Supabase table + function:

  CREATE EXTENSION IF NOT EXISTS vector;

  CREATE TABLE chart_of_accounts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    code        TEXT NOT NULL,          -- e.g. "6010"
    name        TEXT NOT NULL,          -- e.g. "Office Supplies"
    description TEXT,
    embedding   vector(1536) NOT NULL,  -- OpenAI text-embedding-3-small
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
  );

  -- RPC function for cosine similarity search
  CREATE OR REPLACE FUNCTION match_accounts(
    query_embedding vector(1536),
    p_tenant_id     UUID,
    match_threshold FLOAT,
    match_count     INT
  )
  RETURNS TABLE (id UUID, code TEXT, name TEXT, description TEXT, similarity FLOAT)
  LANGUAGE sql STABLE AS $$
    SELECT id, code, name, description,
           1 - (embedding <=> query_embedding) AS similarity
    FROM   chart_of_accounts
    WHERE  tenant_id = p_tenant_id
      AND  1 - (embedding <=> query_embedding) > match_threshold
    ORDER  BY embedding <=> query_embedding
    LIMIT  match_count;
  $$;
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from openai import OpenAI

from src.config import get_settings
from src.infrastructure.repositories.supabase_client import get_supabase_client

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


@dataclass(frozen=True)
class AccountMatch:
    """Single result returned by the RAG similarity search."""
    code: str
    name: str
    description: str | None
    similarity: float


class VectorRepository:
    """
    Semantic search over the Chart of Accounts using pgvector.

    Usage:
        repo = VectorRepository()
        matches = await repo.find_similar_accounts(
            tenant_id=...,
            query_text="Uber Eats — team lunch",
            top_k=3,
        )
        best = matches[0]  # AccountMatch(code="5010", name="Meals & Entertainment", ...)
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._openai = OpenAI(api_key=settings.openai_api_key.get_secret_value())

    def _embed(self, text: str) -> list[float]:
        response = self._openai.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        return response.data[0].embedding

    async def find_similar_accounts(
        self,
        tenant_id: uuid.UUID,
        query_text: str,
        *,
        top_k: int = 5,
        threshold: float = 0.70,
    ) -> list[AccountMatch]:
        """
        Embed query_text, run cosine similarity via the match_accounts RPC,
        and return the top-k matching Chart-of-Accounts entries.
        """
        embedding = self._embed(query_text)
        client = get_supabase_client()
        result = client.rpc(
            "match_accounts",
            {
                "query_embedding": embedding,
                "p_tenant_id": str(tenant_id),
                "match_threshold": threshold,
                "match_count": top_k,
            },
        ).execute()

        return [
            AccountMatch(
                code=row["code"],
                name=row["name"],
                description=row.get("description"),
                similarity=row["similarity"],
            )
            for row in result.data
        ]

    async def upsert_account_embedding(
        self,
        tenant_id: uuid.UUID,
        code: str,
        name: str,
        description: str | None = None,
    ) -> None:
        """Generate and store/refresh the embedding for a Chart-of-Accounts entry."""
        text = f"{code} {name}" + (f" — {description}" if description else "")
        embedding = self._embed(text)
        client = get_supabase_client()
        client.table("chart_of_accounts").upsert(
            {
                "tenant_id": str(tenant_id),
                "code": code,
                "name": name,
                "description": description,
                "embedding": embedding,
            },
            on_conflict="tenant_id,code",
        ).execute()
