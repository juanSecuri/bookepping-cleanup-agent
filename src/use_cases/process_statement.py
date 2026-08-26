"""
ProcessStatement — PDF → extract → rule CoA → persist + mirror txs → reconcile.

Default path is LOCAL ($0): pdfplumber + keyword CoA. No OpenAI / LlamaParse.
Also extracts opening/closing balances and validates the bank balance chain (cadenazo).
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
from src.infrastructure.reconciliation.statement_chain import (
    StatementPeriodRepository,
    extract_statement_balances,
)
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
    chain_ok: bool | None = None
    chain_paused: bool = False
    chain_alert: str | None = None
    opening_balance: float | None = None
    closing_balance: float | None = None


class ProcessStatementUseCase:
    def __init__(
        self,
        local_pdf: LocalPdfClient | None = None,
        coa: RuleCoAClassifier | None = None,
        movement_repo: BankMovementRepository | None = None,
        transaction_repo: TransactionRepository | None = None,
        reconciler: ReconcileLedgerUseCase | None = None,
        periods: StatementPeriodRepository | None = None,
    ) -> None:
        self._local_pdf = local_pdf or LocalPdfClient()
        self._coa = coa or RuleCoAClassifier()
        self._movements = movement_repo or BankMovementRepository()
        self._transactions = transaction_repo or TransactionRepository()
        self._reconciler = reconciler or ReconcileLedgerUseCase()
        self._periods = periods or StatementPeriodRepository()

    async def execute(
        self,
        file_path: Path,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
        *,
        source_document_id: uuid.UUID | None = None,
    ) -> ProcessingReport:
        settings = get_settings()
        engine = "local"
        raw_text = ""
        if settings.use_local_extraction:
            raw_text = await self._local_pdf.extract_text_async(file_path)
            movements = self._local_pdf._movements_from_text(
                text=raw_text,
                tenant_id=tenant_id,
                bank_name=bank_name,
                bank_account_number=bank_account_number,
                statement_month=statement_month,
                source_file_path=str(file_path),
            )
            if not movements:
                from src.domain.exceptions import ExtractionError

                raise ExtractionError(
                    f"No movements extracted locally from {file_path.name}. "
                    "PDF may be image-only (needs Tesseract sprint) or unfamiliar layout."
                )
        else:
            from src.infrastructure.ocr.llama_parse_client import LlamaParseClient

            engine = "llamaparse"
            movements = await LlamaParseClient().parse_bank_statement(
                file_path, tenant_id, bank_name, bank_account_number, statement_month
            )
            try:
                raw_text = await self._local_pdf.extract_text_async(file_path)
            except Exception:
                raw_text = ""

        opening, closing = extract_statement_balances(raw_text)
        chain = self._periods.upsert_and_validate(
            tenant_id=tenant_id,
            bank_name=bank_name,
            bank_account_number=bank_account_number,
            statement_month=statement_month,
            opening_balance=opening,
            closing_balance=closing,
            movement_count=len(movements),
            source_document_id=source_document_id,
        )
        if chain.alert_message:
            logger.warning("Balance chain: %s", chain.alert_message)

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
            chain_ok=chain.chain_ok,
            chain_paused=chain.paused,
            chain_alert=chain.alert_message,
            opening_balance=float(opening) if opening is not None else None,
            closing_balance=float(closing) if closing is not None else None,
        )

    async def _mirror_transaction(
        self, movement: BankMovement, file_path: Path, engine: str
    ) -> None:
        amount = movement.debit_amount if movement.debit_amount > 0 else movement.credit_amount
        if amount <= 0:
            return
        code = movement.chart_of_accounts_code
        # Bank debit = money out; credit = money in. Equity draws stay EXPENSE-typed
        # for cash direction; emit_period_reports routes equity codes out of P&L.
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
            chart_of_accounts_code=code,
            chart_of_accounts_name=movement.chart_of_accounts_name,
            category_confidence=movement.category_confidence,
            ai_suggested_account_code=code,
            ai_suggested_account_name=movement.chart_of_accounts_name,
            vendor_name=vendor,
            bank_movement_id=movement.id,
            metadata=meta,
        )
        try:
            await self._transactions.save(tx)
        except Exception:
            logger.exception("Failed mirroring movement %s to transaction", movement.id)
