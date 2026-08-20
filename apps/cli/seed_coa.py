"""
Seed a starter Chart of Accounts with OpenAI embeddings.

Usage:
  python -m apps.cli.seed_coa --tenant 00000000-0000-0000-0000-000000000001
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.infrastructure.repositories.vector_repository import VectorRepository

DEFAULT_ACCOUNTS = [
    ("1000", "Cash", "asset", "Cash and cash equivalents"),
    ("1100", "Accounts Receivable", "asset", "Money owed by customers"),
    ("2000", "Accounts Payable", "liability", "Money owed to vendors"),
    ("3000", "Owner Equity", "equity", "Owner capital"),
    ("4000", "Sales Revenue", "income", "Operating income"),
    ("5000", "Cost of Goods Sold", "cogs", "Direct costs of goods sold"),
    ("6000", "Office Supplies", "expense", "Office and admin supplies"),
    ("6100", "Travel & Meals", "expense", "Travel, meals and entertainment"),
    ("6200", "Utilities", "expense", "Electricity, water, internet"),
    ("6300", "Professional Services", "expense", "Legal, accounting, consulting"),
    ("9999", "Uncategorized", "expense", "Needs human review"),
]


async def _run(tenant_id: uuid.UUID) -> None:
    repo = VectorRepository()
    for code, name, account_type, description in DEFAULT_ACCOUNTS:
        await repo.upsert_account_embedding(
            tenant_id=tenant_id,
            code=code,
            name=name,
            account_type=account_type,
            description=description,
        )
        print(f"  seeded {code} {name}")
    print(f"Done — {len(DEFAULT_ACCOUNTS)} accounts for tenant {tenant_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Chart of Accounts embeddings")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    args = parser.parse_args()
    asyncio.run(_run(uuid.UUID(args.tenant)))


if __name__ == "__main__":
    main()
