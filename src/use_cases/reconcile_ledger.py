"""
ReconcileLedger use-case.

Matches unreconciled BankMovements to FinancialTransactions (invoices/expenses)
using a date-window + amount fuzzy matching algorithm.

Algorithm:
  For each unreconciled BankMovement:
    1. Find all PENDING FinancialTransactions within ±3 days of movement_date.
    2. Filter by net_amount match (within tolerance, default 0.01).
    3. If exactly one match → mark both as VERIFIED and link them.
    4. If zero or multiple matches → flag for human review.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from src.domain.models.bank_movement import BankMovement
from src.domain.models.enums import TransactionStatus
from src.domain.models.transaction import FinancialTransaction
from src.infrastructure.repositories.transaction_repository import TransactionRepository


@dataclass
class ReconciliationResult:
    matched: list[tuple[BankMovement, FinancialTransaction]]
    unmatched_movements: list[BankMovement]
    ambiguous_movements: list[BankMovement]


class ReconcileLedgerUseCase:
    """
    Reconcile a batch of BankMovements against the pending transaction ledger.

    Usage:
        use_case = ReconcileLedgerUseCase()
        result = await use_case.execute(
            tenant_id=...,
            movements=parsed_movements,
            date_window_days=3,
            amount_tolerance=Decimal("0.01"),
        )
    """

    def __init__(self, transaction_repo: TransactionRepository | None = None) -> None:
        self._repo = transaction_repo or TransactionRepository()

    async def execute(
        self,
        tenant_id: uuid.UUID,
        movements: list[BankMovement],
        *,
        date_window_days: int = 3,
        amount_tolerance: Decimal = Decimal("0.01"),
    ) -> ReconciliationResult:
        pending_txns = await self._repo.list_pending(tenant_id)

        matched: list[tuple[BankMovement, FinancialTransaction]] = []
        unmatched: list[BankMovement] = []
        ambiguous: list[BankMovement] = []

        used_txn_ids: set[uuid.UUID] = set()

        for movement in movements:
            candidates = self._find_candidates(
                movement, pending_txns, date_window_days, amount_tolerance, used_txn_ids
            )
            if len(candidates) == 1:
                txn = candidates[0]
                used_txn_ids.add(txn.id)
                reconciled_txn = txn.mark_verified(
                    chart_code=txn.chart_of_accounts_code or "",
                    confidence=txn.category_confidence or 0.0,
                ).model_copy(update={"bank_movement_id": movement.id})
                await self._repo.save(reconciled_txn)
                matched.append((movement.mark_reconciled(transaction_id=txn.id), reconciled_txn))
            elif len(candidates) == 0:
                unmatched.append(movement)
            else:
                ambiguous.append(movement)

        return ReconciliationResult(
            matched=matched,
            unmatched_movements=unmatched,
            ambiguous_movements=ambiguous,
        )

    @staticmethod
    def _find_candidates(
        movement: BankMovement,
        transactions: list[FinancialTransaction],
        date_window: int,
        tolerance: Decimal,
        used_ids: set[uuid.UUID],
    ) -> list[FinancialTransaction]:
        movement_amount = abs(movement.net_amount)
        window = timedelta(days=date_window)

        return [
            t for t in transactions
            if t.id not in used_ids
            and abs(t.transaction_date - movement.movement_date) <= window
            and abs(t.amount - movement_amount) <= tolerance
            and t.status == TransactionStatus.PENDING_REVIEW
        ]
