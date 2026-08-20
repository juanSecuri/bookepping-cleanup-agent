"""
ClosePeriod use-case.

Aggregates VERIFIED transactions for a fiscal period into a closed MonthlyLedger.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from src.domain.exceptions import BookkeepingError
from src.domain.models.enums import AccountType, TransactionStatus, TransactionType
from src.domain.models.monthly_ledger import LedgerEntry, MonthlyLedger
from src.infrastructure.repositories.monthly_ledger_repository import MonthlyLedgerRepository
from src.infrastructure.repositories.transaction_repository import TransactionRepository


class PeriodAlreadyClosedError(BookkeepingError):
    pass


class ClosePeriodUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository | None = None,
        ledger_repo: MonthlyLedgerRepository | None = None,
    ) -> None:
        self._transactions = transaction_repo or TransactionRepository()
        self._ledgers = ledger_repo or MonthlyLedgerRepository()

    async def execute(
        self,
        tenant_id: uuid.UUID,
        fiscal_period: str,
        currency: str = "USD",
    ) -> MonthlyLedger:
        existing = await self._ledgers.get_by_period(tenant_id, fiscal_period)
        if existing is not None and existing.status == "closed":
            raise PeriodAlreadyClosedError(
                f"Period {fiscal_period} is already closed for tenant {tenant_id}."
            )

        all_txns = await self._transactions.list_by_tenant(tenant_id, limit=10000)
        period_txns = [
            t
            for t in all_txns
            if str(t.transaction_date)[:7] == fiscal_period
            and t.status == TransactionStatus.VERIFIED
        ]

        if not period_txns:
            raise BookkeepingError(
                f"No verified transactions found for period {fiscal_period}. "
                "Verify and approve transactions before closing the period."
            )

        aggregates: dict[str, dict] = defaultdict(
            lambda: {
                "total_debit": Decimal("0"),
                "total_credit": Decimal("0"),
                "transaction_count": 0,
                "account_name": "",
                "account_type": AccountType.EXPENSE,
            }
        )

        for tx in period_txns:
            code = tx.chart_of_accounts_code or "9999"
            name = tx.chart_of_accounts_name or "Sin clasificar"
            account_type = self._infer_account_type(tx.transaction_type)
            agg = aggregates[code]
            agg["account_name"] = name
            agg["account_type"] = account_type
            agg["transaction_count"] += 1
            if tx.transaction_type == TransactionType.INCOME:
                agg["total_credit"] += tx.amount
            else:
                agg["total_debit"] += tx.amount

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

        for tx in period_txns:
            await self._transactions.save(tx.mark_closed(fiscal_period))

        ledger = MonthlyLedger(
            id=existing.id if existing else uuid.uuid4(),
            tenant_id=tenant_id,
            fiscal_period=fiscal_period,
            currency=currency.upper(),
            entries=entries,
            transaction_count=len(period_txns),
            status="closed",
            closed_at=datetime.utcnow(),
        )
        return await self._ledgers.save(ledger)

    @staticmethod
    def _infer_account_type(tx_type: TransactionType) -> AccountType:
        mapping = {
            TransactionType.INCOME: AccountType.INCOME,
            TransactionType.EXPENSE: AccountType.EXPENSE,
            TransactionType.TRANSFER: AccountType.ASSET,
            TransactionType.JOURNAL_ENTRY: AccountType.EQUITY,
        }
        return mapping.get(tx_type, AccountType.EXPENSE)
