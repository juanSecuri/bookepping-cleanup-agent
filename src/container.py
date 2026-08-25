"""Composition root — local/free extraction by default (no paid AI required)."""
from __future__ import annotations

from functools import lru_cache

from src.infrastructure.classification.rule_coa import RuleCoAClassifier
from src.infrastructure.ocr.local_pdf_client import LocalPdfClient
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.monthly_ledger_repository import MonthlyLedgerRepository
from src.infrastructure.repositories.transaction_repository import TransactionRepository
from src.use_cases.close_period import ClosePeriodUseCase
from src.use_cases.generate_financial_statements import GenerateFinancialStatementsUseCase
from src.use_cases.ingest_document import IngestDocumentUseCase
from src.use_cases.process_statement import ProcessStatementUseCase
from src.use_cases.reconcile_ledger import ReconcileLedgerUseCase


class AppContainer:
    """Lazy DI container. Prefer this over constructing use-cases in route handlers."""

    def __init__(self) -> None:
        self.local_pdf = LocalPdfClient()
        self.coa = RuleCoAClassifier()

        self.transactions = TransactionRepository()
        self.movements = BankMovementRepository()
        self.ledgers = MonthlyLedgerRepository()

        self.reconcile = ReconcileLedgerUseCase(
            transaction_repo=self.transactions,
            movement_repo=self.movements,
        )
        self.ingest = IngestDocumentUseCase(
            transaction_repo=self.transactions,
            movement_repo=self.movements,
            local_pdf=self.local_pdf,
            coa=self.coa,
        )
        self.process_statement = ProcessStatementUseCase(
            local_pdf=self.local_pdf,
            coa=self.coa,
            movement_repo=self.movements,
            transaction_repo=self.transactions,
            reconciler=self.reconcile,
        )
        self.close_period = ClosePeriodUseCase(
            transaction_repo=self.transactions,
            ledger_repo=self.ledgers,
        )
        self.statements = GenerateFinancialStatementsUseCase()


@lru_cache(maxsize=1)
def get_container() -> AppContainer:
    return AppContainer()
