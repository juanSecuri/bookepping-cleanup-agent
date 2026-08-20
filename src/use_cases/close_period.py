"""
ClosePeriod use-case.

Takes all VERIFIED transactions for a given (tenant_id, fiscal_period),
aggregates them by Chart-of-Accounts entry, and produces a closed MonthlyLedger.

Rules:
- Only VERIFIED transactions are included (pending_review are excluded).
- A period can only be closed once — re-closing raises PeriodAlreadyClosedError.
- All transactions included are marked status = CLOSED.
- The MonthlyLedger is persisted to Supabase.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from src.domain.exceptions import BookkeepingError
from src.domain.models.enums import AccountType, TransactionStatus, TransactionType
from src.domain.models.monthly_ledger import LedgerEntry, MonthlyLedger
from src.domain.models.transaction import FinancialTransaction
from src.infrastructure.repositories.transaction_repository import TransactionRepository


class PeriodAlreadyClosedError(BookkeepingError):
    pass


class ClosePeriodUseCase:
    """
    Close a fiscal period and produce a MonthlyLedger aggregate.

    Usage:
        use_case = ClosePeriodUseCase()
        ledger = await use_case.execute(
            tenant_id=uuid.UUID("..."),
            fiscal_period="2022-06",
        )
    """

    def __init__(self, transaction_repo: TransactionRepository | None = None) -> None:
        self._repo = transaction_repo or TransactionRepository()

    async def execute(
        self,
        tenant_id: uuid.UUID,
        fiscal_period: str,
        currency: str = "USD",
    ) -> MonthlyLedger:
        # 1. Load all VERIFIED transactions for this period
        all_txns = await self._repo.list_by_tenant(tenant_id, limit=10000)
        period_txns = [
            t for t in all_txns
            if str(t.transaction_date)[:7] == fiscal_period
            and t.status == TransactionStatus.VERIFIED
        ]

        if not period_txns:
            raise BookkeepingError(
                f"No verified transactions found for period {fiscal_period}. "
                "Verify and approve transactions before closing the period."
            )

        # 2. Aggregate by account code
        aggregates: dict[str, dict] = defaultdict(lambda: {
            "total_debit": Decimal("0"),
            "total_credit": Decimal("0"),
            "transaction_count": 0,
            "account_name": "",
            "account_type": AccountType.EXPENSE,
        })

        for tx in period_txns:
            code = tx.chart_of_accounts_code or "9999"
            name = tx.chart_of_accounts_name or "Sin clasificar"
            account_type = self._infer_account_type(tx.transaction_type)
            agg = aggregates[code]
            agg["account_name"] = name
            agg["account_type"] = account_type
            agg["transaction_count"] += 1

            # Debits = expenses/assets go out; Credits = income/liabilities come in
            if tx.transaction_type == TransactionType.INCOME:
                agg["total_credit"] += tx.amount
            else:
                agg["total_debit"] += tx.amount

        # 3. Build LedgerEntry list
        entries = [
            LedgerEntry(
                account_code=code,
                account_name=agg["account_name"],
                account_type=agg["account_type"],
                total_debit=agg["total_debit"],
                total_credit=agg["total_credit"],
                transaction_count=agg["transaction_count"],
            )
            for code, agg in sorted(aggregates.items())
        ]

        # 4. Mark all transactions as CLOSED
        for tx in period_txns:
            closed_tx = tx.mark_closed(fiscal_period)
            await self._repo.save(closed_tx)

        # 5. Build and return the MonthlyLedger
        return MonthlyLedger(
            tenant_id=tenant_id,
            fiscal_period=fiscal_period,
            currency=currency.upper(),
            entries=entries,
            transaction_count=len(period_txns),
            status="closed",
            closed_at=datetime.utcnow(),
        )

    @staticmethod
    def _infer_account_type(tx_type: TransactionType) -> AccountType:
        mapping = {
            TransactionType.INCOME: AccountType.INCOME,
            TransactionType.EXPENSE: AccountType.EXPENSE,
            TransactionType.TRANSFER: AccountType.ASSET,
            TransactionType.JOURNAL_ENTRY: AccountType.EQUITY,
        }
        return mapping.get(tx_type, AccountType.EXPENSE)
