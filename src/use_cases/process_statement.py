"""
ProcessStatement use-case.

PDF → parse → RAG categorise → persist movements + mirror transactions → reconcile.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.domain.models.bank_movement import BankMovement
from src.domain.models.enums import DocumentSource, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.ocr.llama_parse_client import LlamaParseClient
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.transaction_repository import TransactionRepository
from src.infrastructure.repositories.vector_repository import VectorRepository
from src.use_cases.reconcile_ledger import ReconcileLedgerUseCase, ReconciliationResult

logger = logging.getLogger(__name__)


@dataclass
class ProcessingReport:
    total_movements: int
    categorised: int
    reconciled: int
    unmatched: int
    ambiguous: int
    movements: list[BankMovement] = field(default_factory=list)
    reconciliation: ReconciliationResult | None = None


class ProcessStatementUseCase:
    def __init__(
        self,
        llama_client: LlamaParseClient | None = None,
        vector_repo: VectorRepository | None = None,
        movement_repo: BankMovementRepository | None = None,
        transaction_repo: TransactionRepository | None = None,
        reconciler: ReconcileLedgerUseCase | None = None,
    ) -> None:
        self._llama = llama_client or LlamaParseClient()
        self._vector = vector_repo or VectorRepository()
        self._movements = movement_repo or BankMovementRepository()
        self._transactions = transaction_repo or TransactionRepository()
        self._reconciler = reconciler or ReconcileLedgerUseCase()

    async def execute(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
    ) -> ProcessingReport:
        movements = await self._llama.parse_bank_statement(
            file_path, tenant_id, bank_name, bank_account_number, statement_month
        )

        categorised: list[BankMovement] = []
        for movement in movements:
            try:
                matches = await self._vector.find_similar_accounts(
                    tenant_id=tenant_id,
                    query_text=movement.description,
                    top_k=1,
                    threshold=0.72,
                )
                if matches:
                    best = matches[0]
                    movement = movement.model_copy(
                        update={
                            "chart_of_accounts_code": best.code,
                            "chart_of_accounts_name": best.name,
                            "category_confidence": best.similarity,
                        }
                    )
            except Exception:
                logger.exception(
                    "RAG categorisation failed for movement %s", movement.id
                )
            saved_mov = await self._movements.save(movement)
            categorised.append(saved_mov)
            await self._mirror_transaction(saved_mov, file_path)

        categorised_count = sum(
            1 for m in categorised if m.chart_of_accounts_code is not None
        )

        reconciliation = await self._reconciler.execute(
            tenant_id=tenant_id,
            movements=categorised,
        )

        return ProcessingReport(
            total_movements=len(movements),
            categorised=categorised_count,
            reconciled=len(reconciliation.matched),
            unmatched=len(reconciliation.unmatched_movements),
            ambiguous=len(reconciliation.ambiguous_movements),
            movements=categorised,
            reconciliation=reconciliation,
        )

    async def _mirror_transaction(self, movement: BankMovement, file_path: Path) -> None:
        """Create a reviewable FinancialTransaction for each bank line."""
        amount = movement.debit_amount if movement.debit_amount > 0 else movement.credit_amount
        if amount <= 0:
            return
        tx_type = (
            TransactionType.EXPENSE
            if movement.debit_amount > 0
            else TransactionType.INCOME
        )
        vendor = movement.description.split("  ")[0][:128]
        meta = ExtractionMetadata(
            source=DocumentSource.BANK_STATEMENT,
            raw_file_path=str(file_path),
            extraction_model="llamaparse+statement",
            confidence_score=float(movement.category_confidence or 0.85),
            raw_text=movement.description,
        )
        tx = FinancialTransaction(
            tenant_id=movement.tenant_id,
            transaction_date=movement.movement_date,
            description=movement.description,
            amount=amount,
            currency=movement.currency,
            transaction_type=tx_type,
            chart_of_accounts_code=movement.chart_of_accounts_code,
            chart_of_accounts_name=movement.chart_of_accounts_name,
            category_confidence=movement.category_confidence,
            ai_suggested_account_code=movement.chart_of_accounts_code,
            ai_suggested_account_name=movement.chart_of_accounts_name,
            vendor_name=vendor,
            bank_movement_id=movement.id,
            metadata=meta,
        )
        try:
            await self._transactions.save(tx)
        except Exception:
            logger.exception("Failed mirroring movement %s to transaction", movement.id)
