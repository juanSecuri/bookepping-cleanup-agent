"""
pgvector-backed Chart-of-Accounts semantic search (RAG).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from src.infrastructure.llm.openai_client import OpenAIClient
from src.infrastructure.repositories.supabase_client import get_supabase_client


@dataclass(frozen=True)
class AccountMatch:
    code: str
    name: str
    description: str | None
    similarity: float
    account_type: str | None = None


class VectorRepository:
    def __init__(self, openai_client: OpenAIClient | None = None) -> None:
        self._openai = openai_client or OpenAIClient()

    async def find_similar_accounts(
        self,
        tenant_id: uuid.UUID,
        query_text: str,
        *,
        top_k: int = 5,
        threshold: float = 0.70,
    ) -> list[AccountMatch]:
        embedding = self._openai.embed(query_text)
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
                account_type=row.get("account_type"),
            )
            for row in result.data
        ]

    async def upsert_account_embedding(
        self,
        tenant_id: uuid.UUID,
        code: str,
        name: str,
        account_type: str,
        description: str | None = None,
    ) -> None:
        text = f"{code} {name}" + (f" — {description}" if description else "")
        embedding = self._openai.embed(text)
        client = get_supabase_client()
        client.table("chart_of_accounts").upsert(
            {
                "tenant_id": str(tenant_id),
                "code": code,
                "name": name,
                "account_type": account_type,
                "description": description,
                "embedding": embedding,
            },
            on_conflict="tenant_id,code",
        ).execute()
