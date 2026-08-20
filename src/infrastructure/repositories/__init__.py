"""
Infrastructure repositories — public exports.

Import from here to avoid coupling use-cases to concrete file paths.

  from src.infrastructure.repositories import (
      TransactionRepository,
      BankMovementRepository,
      MonthlyLedgerRepository,
      VectorRepository,
  )
"""
from src.infrastructure.repositories.transaction_repository import TransactionRepository
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.monthly_ledger_repository import MonthlyLedgerRepository
from src.infrastructure.repositories.vector_repository import VectorRepository

__all__ = [
    "TransactionRepository",
    "BankMovementRepository",
    "MonthlyLedgerRepository",
    "VectorRepository",
]
