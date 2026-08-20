"""Shared enumerations used across all domain models."""
from enum import Enum

class TransactionStatus(str, Enum):
    PENDING_REVIEW = "pending_review"   # Extracted, not yet validated
    VERIFIED = "verified"               # Human-approved by accountant
    CLOSED = "closed"                   # Included in a closed monthly ledger

class DocumentSource(str, Enum):
    PHOTO = "photo"
    PDF = "pdf"
    AUDIO = "audio"
    BANK_STATEMENT = "bank_statement"
    MANUAL = "manual"

class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    JOURNAL_ENTRY = "journal_entry"

class AccountType(str, Enum):
    """Standard accounting classification for Chart of Accounts entries."""
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"
    COST_OF_GOODS_SOLD = "cogs"
