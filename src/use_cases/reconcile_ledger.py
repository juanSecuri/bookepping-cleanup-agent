"""
ReconcileLedger use-case.

Matches unreconciled BankMovements to pending FinancialTransactions
using a date-window + amount fuzzy match.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from src.domain.models.bank_movement import BankMovement
from src.domain.models.enums import TransactionStatus
from src.domain.models.transaction import FinancialTransaction
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.transaction_repository import TransactionRepository


@dataclass
class ReconciliationResult:
    matched: list[tuple[BankMovement, FinancialTransaction]]
    unmatched_movements: list[BankMovement]
    ambiguous_movements: list[BankMovement]


class ReconcileLedgerUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository | None = None,
        movement_repo: BankMovementRepository | None = None,
    ) -> None:
        self._transactions = transaction_repo or TransactionRepository()
        self._movements = movement_repo or BankMovementRepository()

    async def execute(
        self,
        tenant_id: uuid.UUID,
        movements: list[BankMovement],
        *,
        date_window_days: int = 3,
        amount_tolerance: Decimal = Decimal("0.01"),
    ) -> ReconciliationResult:
        pending_txns = await self._transactions.list_pending(tenant_id)

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
                chart_code = txn.chart_of_accounts_code or movement.chart_of_accounts_code or "9999"
                chart_name = (
                    txn.chart_of_accounts_name
                    or movement.chart_of_accounts_name
                    or "Sin clasificar"
                )
                confidence = txn.category_confidence or movement.category_confidence or 0.5
                reconciled_txn = txn.mark_verified(chart_code, chart_name, confidence).model_copy(
                    update={"bank_movement_id": movement.id}
                )
                saved_txn = await self._transactions.save(reconciled_txn)
                saved_movement = await self._movements.save(
                    movement.mark_reconciled(transaction_id=txn.id)
                )
                matched.append((saved_movement, saved_txn))
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
            t
            for t in transactions
            if t.id not in used_ids
            and abs(t.transaction_date - movement.movement_date) <= window
            and abs(t.amount - movement_amount) <= tolerance
            and t.status == TransactionStatus.PENDING_REVIEW
        ]
