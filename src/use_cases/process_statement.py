"""
ProcessStatement — PDF → extract → rule CoA → persist + mirror txs → reconcile.

Default path is LOCAL ($0): pdfplumber + keyword CoA. No OpenAI / LlamaParse.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from src.config import get_settings
from src.domain.models.bank_movement import BankMovement
from src.domain.models.enums import DocumentSource, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.classification.rule_coa import RuleCoAClassifier
from src.infrastructure.ocr.local_pdf_client import LocalPdfClient
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.transaction_repository import TransactionRepository
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
    extraction_engine: str = "local"


class ProcessStatementUseCase:
    def __init__(
        self,
        local_pdf: LocalPdfClient | None = None,
        coa: RuleCoAClassifier | None = None,
        movement_repo: BankMovementRepository | None = None,
        transaction_repo: TransactionRepository | None = None,
        reconciler: ReconcileLedgerUseCase | None = None,
    ) -> None:
        self._local_pdf = local_pdf or LocalPdfClient()
        self._coa = coa or RuleCoAClassifier()
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
        settings = get_settings()
        engine = "local"
        if settings.use_local_extraction:
            movements = await self._local_pdf.parse_bank_statement_async(
                file_path, tenant_id, bank_name, bank_account_number, statement_month
            )
        else:
            # Optional cloud fallback only if explicitly EXTRACTION_MODE=cloud
            from src.infrastructure.ocr.llama_parse_client import LlamaParseClient

            engine = "llamaparse"
            movements = await LlamaParseClient().parse_bank_statement(
                file_path, tenant_id, bank_name, bank_account_number, statement_month
            )

        categorised: list[BankMovement] = []
        for movement in movements:
            try:
                match = self._coa.classify(tenant_id, movement.description)
                movement = movement.model_copy(
                    update={
                        "chart_of_accounts_code": match.code,
                        "chart_of_accounts_name": match.name,
                        "category_confidence": match.confidence,
                    }
                )
            except Exception:
                logger.exception("Rule CoA failed for movement %s", movement.id)
            saved_mov = await self._movements.save(movement)
            categorised.append(saved_mov)
            await self._mirror_transaction(saved_mov, file_path, engine)

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
            extraction_engine=engine,
        )

    async def _mirror_transaction(
        self, movement: BankMovement, file_path: Path, engine: str
    ) -> None:
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
            extraction_model=f"{engine}+rules_coa",
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
