"""Composition root — wires concrete adapters for the application layer."""
from __future__ import annotations

from functools import lru_cache

from src.infrastructure.llm.openai_client import OpenAIClient
from src.infrastructure.llm.voice_client import VoiceClient
from src.infrastructure.ocr.llama_parse_client import LlamaParseClient
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.monthly_ledger_repository import MonthlyLedgerRepository
from src.infrastructure.repositories.transaction_repository import TransactionRepository
from src.infrastructure.repositories.vector_repository import VectorRepository
from src.use_cases.close_period import ClosePeriodUseCase
from src.use_cases.generate_financial_statements import GenerateFinancialStatementsUseCase
from src.use_cases.ingest_document import IngestDocumentUseCase
from src.use_cases.process_statement import ProcessStatementUseCase
from src.use_cases.reconcile_ledger import ReconcileLedgerUseCase


class AppContainer:
    """Lazy DI container. Prefer this over constructing use-cases in route handlers."""

    def __init__(self) -> None:
        self.openai = OpenAIClient()
        self.voice = VoiceClient(openai_client=self.openai)
        self.llama = LlamaParseClient()

        self.transactions = TransactionRepository()
        self.movements = BankMovementRepository()
        self.ledgers = MonthlyLedgerRepository()
        self.vectors = VectorRepository(openai_client=self.openai)

        self.reconcile = ReconcileLedgerUseCase(
            transaction_repo=self.transactions,
            movement_repo=self.movements,
        )
        self.ingest = IngestDocumentUseCase(
            transaction_repo=self.transactions,
            movement_repo=self.movements,
            openai_client=self.openai,
            voice_client=self.voice,
            llama_client=self.llama,
        )
        self.process_statement = ProcessStatementUseCase(
            llama_client=self.llama,
            vector_repo=self.vectors,
            movement_repo=self.movements,
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
