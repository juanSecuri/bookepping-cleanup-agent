"""Full bookkeeper pass: upgrade rules, reclassify ≤ max year, auto-verify high confidence.

Juan (or CPA) only reviews leftovers / low-confidence rows.
"""
from __future__ import annotations

import uuid
from typing import Any

from src.domain.models.enums import TransactionStatus, TransactionType
from src.infrastructure.classification.rule_coa import (
    OTHER_INCOME_CODE,
    SUSPENSE_CODE,
    RuleCoAClassifier,
    clean_description,
    looks_like_expense_merchant,
)
from src.infrastructure.drive.year_policy import parse_max_fiscal_year
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.transaction_repository import TransactionRepository
from src.infrastructure.repositories.workspace_repository import WorkspaceRepository


class BookkeeperPassUseCase:
    def __init__(self) -> None:
        self._tx = TransactionRepository()
        self._workspaces = WorkspaceRepository()

    async def execute(
        self,
        workspace_id: uuid.UUID,
        *,
        auto_approve_min_confidence: float = 0.72,
        limit: int = 8000,
    ) -> dict[str, Any]:
        ws = await self._workspaces.get(workspace_id)
        ceiling = ws.max_fiscal_year if ws and ws.max_fiscal_year is not None else None
        if ceiling is None:
            client = get_supabase_client()
            row = (
                client.table("clients")
                .select("max_fiscal_year")
                .eq("id", str(workspace_id))
                .limit(1)
                .execute()
            )
            if row.data:
                ceiling = parse_max_fiscal_year(row.data[0].get("max_fiscal_year"))
        if ceiling is None:
            ceiling = 2025  # CPA default when unset for bookkeeper pass scope

        date_to = f"{ceiling}-12-31"
        coa = RuleCoAClassifier()
        income_upgrade = coa.upgrade_income_seed_rules(workspace_id)
        expense_upgrade = coa.upgrade_expense_seed_rules(workspace_id)

        items = await self._tx.list_by_tenant_date_range(
            workspace_id,
            date_from=None,
            date_to=date_to,
            limit=limit,
        )

        categorized = 0
        auto_approved = 0
        left_suspense = 0
        fixed_other_income = 0
        income_n = 0
        expense_n = 0
        skipped = 0

        for tx in items:
            code = tx.chart_of_accounts_code or tx.ai_suggested_account_code or ""
            conf = float(tx.category_confidence or 0)
            cleaned = clean_description(tx.description or "")
            needs_work = (
                tx.status == TransactionStatus.PENDING_REVIEW
                or code == SUSPENSE_CODE
                or conf < 0.4
                or (
                    code == OTHER_INCOME_CODE
                    and looks_like_expense_merchant(cleaned)
                )
                or (
                    tx.transaction_type == TransactionType.INCOME
                    and code == "1010"
                )
            )
            if not needs_work:
                skipped += 1
                continue

            direction = (
                "income" if tx.transaction_type == TransactionType.INCOME else "expense"
            )
            match = coa.classify(workspace_id, tx.description or "", direction=direction)

            if match.code == OTHER_INCOME_CODE and looks_like_expense_merchant(cleaned):
                match = coa.classify(
                    workspace_id, tx.description or "", direction="expense"
                )
                fixed_other_income += 1

            updates: dict[str, Any] = {
                "chart_of_accounts_code": match.code,
                "chart_of_accounts_name": match.name,
                "category_confidence": match.confidence,
                "ai_suggested_account_code": match.code,
                "ai_suggested_account_name": match.name,
            }
            if match.vendor and not tx.vendor_name:
                updates["vendor_name"] = match.vendor

            saved = await self._tx.save(tx.model_copy(update=updates))
            categorized += 1
            if direction == "income":
                income_n += 1
            else:
                expense_n += 1

            if match.code == SUSPENSE_CODE:
                left_suspense += 1
                continue

            if (
                float(match.confidence) >= auto_approve_min_confidence
                and match.code not in {SUSPENSE_CODE, OTHER_INCOME_CODE}
                and saved.status == TransactionStatus.PENDING_REVIEW
            ):
                await self._tx.save(
                    saved.mark_verified(
                        match.code, match.name, float(match.confidence)
                    )
                )
                auto_approved += 1

        return {
            "max_year": ceiling,
            "scanned": len(items),
            "categorized": categorized,
            "auto_approved": auto_approved,
            "left_suspense": left_suspense,
            "fixed_other_income": fixed_other_income,
            "skipped_ok": skipped,
            "income": income_n,
            "expense": expense_n,
            "income_upgrade": income_upgrade,
            "expense_upgrade": expense_upgrade,
            "engine": "bookkeeper_pass+local_rules",
            "note": "High-confidence rows auto-verified; review remaining pending/suspense.",
        }
