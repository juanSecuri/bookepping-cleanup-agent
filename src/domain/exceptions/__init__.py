"""Domain-level accounting exceptions — no external dependencies."""

from __future__ import annotations


class BookkeepingError(Exception):
    """Base exception for all domain errors."""


class InvalidTransactionError(BookkeepingError):
    """Raised when a transaction fails domain validation."""


class DuplicateTransactionError(BookkeepingError):
    """Raised when an identical transaction already exists in the ledger."""


class ReconciliationError(BookkeepingError):
    """Raised when a bank movement cannot be matched to a supporting document."""


class CategorizationError(BookkeepingError):
    """Raised when the RAG engine cannot assign a Chart-of-Accounts category."""


class ExtractionError(BookkeepingError):
    """Raised when a document (image, PDF, audio) cannot be parsed."""


class QuickBooksExportError(BookkeepingError):
    """Raised when a verified transaction fails to sync with QuickBooks Online."""
