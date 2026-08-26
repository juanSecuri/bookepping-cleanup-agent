"""Shared enumerations used across all domain models."""
from enum import Enum


class TransactionStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    VERIFIED = "verified"
    CLOSED = "closed"
    REJECTED = "rejected"


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
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    INCOME = "income"
    EXPENSE = "expense"
    COST_OF_GOODS_SOLD = "cogs"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    FAILED = "failed"


class DocumentFileType(str, Enum):
    IMAGE = "image"
    PDF = "pdf"
    CSV = "csv"
    AUDIO = "audio"
    OTHER = "other"
