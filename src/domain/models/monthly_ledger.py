"""
MonthlyLedger — aggregate that represents a fully closed accounting period.

One MonthlyLedger per (tenant_id, fiscal_period). It is created by the
close_period use-case once all transactions for that month are VERIFIED.

It stores the summarised totals per Chart-of-Accounts entry so that
Balance Sheet and Income Statement can be computed without re-scanning
every individual transaction.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from src.domain.models.enums import AccountType


class LedgerEntry(BaseModel):
    """Aggregated debit/credit total for one account within a period."""
    model_config = ConfigDict(frozen=True)

    account_code: str
    account_name: str
    account_type: AccountType
    total_debit: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    total_credit: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    transaction_count: int = Field(default=0, ge=0)

    @property
    def net_balance(self) -> Decimal:
        """
        Normal balance convention:
          Assets / Expenses / COGS  → debit increases (debit - credit)
          Liabilities / Equity / Income → credit increases (credit - debit)
        """
        if self.account_type in (AccountType.ASSET, AccountType.EXPENSE, AccountType.COST_OF_GOODS_SOLD):
            return self.total_debit - self.total_credit
        return self.total_credit - self.total_debit


class MonthlyLedger(BaseModel):
    """
    Closed accounting period summary for one tenant.

    Invariant: once status = 'closed' this record must be immutable.
    Amendments require creating an adjusting journal entry for the NEXT period.
    """
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    fiscal_period: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM")
    currency: str = Field(default="USD", min_length=3, max_length=3)

    entries: list[LedgerEntry] = Field(default_factory=list)
    transaction_count: int = Field(default=0, ge=0)
    status: str = Field(default="open", pattern="^(open|closed)$")

    closed_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("currency")
    @classmethod
    def currency_uppercase(cls, v: str) -> str:
        return v.upper()

    # ── Computed aggregates used by financial statements ───────────────────
    def entries_by_type(self, account_type: AccountType) -> list[LedgerEntry]:
        return [e for e in self.entries if e.account_type == account_type]

    @property
    def total_income(self) -> Decimal:
        return sum((e.net_balance for e in self.entries_by_type(AccountType.INCOME)), Decimal("0"))

    @property
    def total_cogs(self) -> Decimal:
        return sum((e.net_balance for e in self.entries_by_type(AccountType.COST_OF_GOODS_SOLD)), Decimal("0"))

    @property
    def gross_profit(self) -> Decimal:
        return self.total_income - self.total_cogs

    @property
    def total_expenses(self) -> Decimal:
        return sum((e.net_balance for e in self.entries_by_type(AccountType.EXPENSE)), Decimal("0"))

    @property
    def net_income(self) -> Decimal:
        return self.gross_profit - self.total_expenses

    @property
    def total_assets(self) -> Decimal:
        return sum((e.net_balance for e in self.entries_by_type(AccountType.ASSET)), Decimal("0"))

    @property
    def total_liabilities(self) -> Decimal:
        return sum((e.net_balance for e in self.entries_by_type(AccountType.LIABILITY)), Decimal("0"))

    @property
    def total_equity(self) -> Decimal:
        return sum((e.net_balance for e in self.entries_by_type(AccountType.EQUITY)), Decimal("0"))
