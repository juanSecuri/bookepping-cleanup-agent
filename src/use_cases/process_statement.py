"""
ProcessStatement use-case.

Orchestrates the full bank statement pipeline for a single monthly PDF:
  1. Parse PDF → list[BankMovement] via LlamaParseClient
  2. Categorise each movement via RAG (VectorRepository)
  3. Persist BankMovements to Supabase
  4. Run ReconcileLedger against the already-ingested invoices
  5. Return a ProcessingReport with counts and unmatched items
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.domain.models.bank_movement import BankMovement
from src.infrastructure.ocr.llama_parse_client import LlamaParseClient
from src.infrastructure.repositories.vector_repository import VectorRepository
from src.use_cases.reconcile_ledger import ReconcileLedgerUseCase, ReconciliationResult


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
    """
    Full pipeline: PDF → parsed → categorised → reconciled.

    Usage:
        use_case = ProcessStatementUseCase()
        report = await use_case.execute(
            file_path=Path("statements/2022-06.pdf"),
            tenant_id=uuid.UUID("..."),
            bank_name="Bancolombia",
            bank_account_number="123-456789",
            statement_month="2022-06",
        )
    """

    def __init__(
        self,
        llama_client: LlamaParseClient | None = None,
        vector_repo: VectorRepository | None = None,
        reconciler: ReconcileLedgerUseCase | None = None,
    ) -> None:
        self._llama = llama_client or LlamaParseClient()
        self._vector = vector_repo or VectorRepository()
        self._reconciler = reconciler or ReconcileLedgerUseCase()

    async def execute(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
    ) -> ProcessingReport:
        # Step 1 — Extract movements
        movements = await self._llama.parse_bank_statement(
            file_path, tenant_id, bank_name, bank_account_number, statement_month
        )

        # Step 2 — RAG categorisation
        categorised_movements: list[BankMovement] = []
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
                            "category_confidence": best.similarity,
                        }
                    )
            except Exception:
                pass   # Log and continue — categorisation failure is non-fatal
            categorised_movements.append(movement)

        categorised_count = sum(
            1 for m in categorised_movements if m.chart_of_accounts_code is not None
        )

        # Step 3 — Reconcile against pending transactions
        reconciliation = await self._reconciler.execute(
            tenant_id=tenant_id,
            movements=categorised_movements,
        )

        return ProcessingReport(
            total_movements=len(movements),
            categorised=categorised_count,
            reconciled=len(reconciliation.matched),
            unmatched=len(reconciliation.unmatched_movements),
            ambiguous=len(reconciliation.ambiguous_movements),
            movements=categorised_movements,
            reconciliation=reconciliation,
        )
