"""
Seed Chart of Accounts WITHOUT OpenAI embeddings (free path).

TPC-oriented PMV CoA (aligned to QuickBooks export categories, simplified codes).

  python -m apps.cli.seed_coa --tenant <uuid>
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

DEFAULT_ACCOUNTS = [
    ("1010", "Cash and Cash Equivalents", "asset", "Current Assets"),
    ("1020", "Accounts Receivable", "asset", "Current Assets"),
    ("1030", "Inventory", "asset", "Current Assets"),
    ("1040", "Prepaid Expenses", "asset", "Current Assets"),
    ("1510", "Equipment", "asset", "Fixed Assets"),
    ("1520", "Furniture & Fixtures", "asset", "Fixed Assets"),
    ("1530", "Vehicles", "asset", "Fixed Assets"),
    ("2010", "Accounts Payable", "liability", "Current Liabilities"),
    ("2020", "Accrued Liabilities", "liability", "Current Liabilities"),
    ("2030", "Short-Term Loans", "liability", "Current Liabilities"),
    ("2040", "Taxes Payable", "liability", "Current Liabilities"),
    ("2510", "Long-Term Debt", "liability", "Long-Term Liabilities"),
    ("3010", "Owner's Equity", "equity", "Equity"),
    ("3020", "Retained Earnings", "equity", "Equity"),
    ("3030", "Owner's Distributions", "equity", "Equity"),
    ("4010", "Sales Revenue", "income", "Operating Revenue"),
    ("4020", "Service Revenue", "income", "Operating Revenue"),
    ("4030", "Interest Income", "income", "Other Income"),
    ("4040", "Other Income", "income", "Other Income"),
    ("5010", "Cost of Goods Sold", "cogs", "COGS"),
    ("5020", "Direct Labor", "cogs", "COGS"),
    ("6010", "Salaries & Wages", "expense", "Operating Expenses"),
    ("6020", "Rent Expense", "expense", "Operating Expenses"),
    ("6030", "Utilities", "expense", "Operating Expenses"),
    ("6040", "Office Supplies", "expense", "Operating Expenses"),
    ("6050", "Meals Expense", "expense", "Operating Expenses"),
    ("6055", "Travel", "expense", "Operating Expenses"),
    ("6060", "Advertising", "expense", "Operating Expenses"),
    ("6065", "Social Media Ads", "expense", "Operating Expenses"),
    ("6070", "Legal & Professional Fees", "expense", "Operating Expenses"),
    ("6080", "Insurance", "expense", "Operating Expenses"),
    ("6090", "Repair & Maintenance", "expense", "Operating Expenses"),
    ("6100", "Dues & Subscriptions", "expense", "Operating Expenses"),
    ("6110", "Bank Charges", "expense", "Operating Expenses"),
    ("6120", "Depreciation Expense", "expense", "Operating Expenses"),
    ("6130", "Taxes & Licenses", "expense", "Operating Expenses"),
    ("6140", "Interest Expense", "expense", "Other Expenses"),
    ("6150", "Miscellaneous Expense", "expense", "Other Expenses"),
    ("6160", "Gas & Oil", "expense", "Operating Expenses"),
    ("6170", "Parking & Tolls", "expense", "Operating Expenses"),
    ("9999", "Gastos No Categorizados (Suspense)", "expense", "Suspense"),
]


async def _run(tenant_id: uuid.UUID) -> None:
    from src.infrastructure.repositories.supabase_client import get_supabase_client

    client = get_supabase_client()
    for code, name, account_type, subcategory in DEFAULT_ACCOUNTS:
        client.table("chart_of_accounts").upsert(
            {
                "tenant_id": str(tenant_id),
                "code": code,
                "name": name,
                "account_type": account_type,
                "subcategory": subcategory,
                "is_active": True,
            },
            on_conflict="tenant_id,code",
        ).execute()
        print(f"  seeded {code} {name}")
    from src.infrastructure.classification.rule_coa import RuleCoAClassifier

    clf = RuleCoAClassifier()
    clf.ensure_seed_rules(tenant_id)
    upgrade = clf.upgrade_income_seed_rules(tenant_id)
    upgrade_exp = clf.upgrade_expense_seed_rules(tenant_id)
    print(f"Done — {len(DEFAULT_ACCOUNTS)} accounts + rules for {tenant_id}")
    print(f"  income upgrade: {upgrade}")
    print(f"  expense upgrade: {upgrade_exp}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed CoA without paid embeddings")
    parser.add_argument("--tenant", required=True, help="Workspace / tenant UUID")
    args = parser.parse_args()
    asyncio.run(_run(uuid.UUID(args.tenant)))


if __name__ == "__main__":
    main()
