"""
FinancialStatement domain models.

Two core statements produced by the agent for each closed period:

1. IncomeStatement  — Estado de Resultados (P&L)
   Shows: Revenue → COGS → Gross Profit → Expenses → Net Income

2. BalanceSheet     — Balance General
   Shows: Assets = Liabilities + Equity  (must balance to zero)

Both can be generated for a single month or aggregated across a full year.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from src.domain.models.enums import AccountType


class StatementLineItem(BaseModel):
    """A single line in a financial statement (one account or subtotal)."""
    model_config = ConfigDict(frozen=True)
    account_code: str
    account_name: str
    amount: Decimal
    is_subtotal: bool = False


class IncomeStatement(BaseModel):
    """
    Estado de Resultados / Profit & Loss Statement.

    Covers one fiscal_period (YYYY-MM) or a full year range.
    """
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    period_label: str = Field(..., description="e.g. '2022-06' or '2022 Full Year'")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    # Revenue section
    revenue_lines: list[StatementLineItem] = Field(default_factory=list)
    total_revenue: Decimal = Field(default=Decimal("0"))

    # Cost of Goods Sold
    cogs_lines: list[StatementLineItem] = Field(default_factory=list)
    total_cogs: Decimal = Field(default=Decimal("0"))
    gross_profit: Decimal = Field(default=Decimal("0"))

    # Operating Expenses
    expense_lines: list[StatementLineItem] = Field(default_factory=list)
    total_expenses: Decimal = Field(default=Decimal("0"))

    # Bottom line
    net_income: Decimal = Field(default=Decimal("0"))

    @model_validator(mode="after")
    def verify_net_income(self) -> "IncomeStatement":
        expected = self.gross_profit - self.total_expenses
        if abs(self.net_income - expected) > Decimal("0.02"):
            raise ValueError(
                f"net_income {self.net_income} does not match "
                f"gross_profit - expenses = {expected}"
            )
        return self


class BalanceSheetSection(BaseModel):
    model_config = ConfigDict(frozen=True)
    lines: list[StatementLineItem] = Field(default_factory=list)
    total: Decimal = Field(default=Decimal("0"))


class BalanceSheet(BaseModel):
    """
    Balance General — Assets = Liabilities + Equity.

    Generated at the end of each closed period.
    Retains prior-period retained earnings automatically.
    """
    model_config = ConfigDict(frozen=True)

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID
    period_label: str = Field(..., description="e.g. '2022-06' or '2022-12-31'")
    currency: str = Field(default="USD", min_length=3, max_length=3)
    generated_at: datetime = Field(default_factory=datetime.utcnow)

    assets: BalanceSheetSection = Field(default_factory=BalanceSheetSection)
    liabilities: BalanceSheetSection = Field(default_factory=BalanceSheetSection)
    equity: BalanceSheetSection = Field(default_factory=BalanceSheetSection)

    # Retained earnings carried from prior periods
    retained_earnings: Decimal = Field(default=Decimal("0"))
    current_period_net_income: Decimal = Field(default=Decimal("0"))

    @property
    def total_liabilities_and_equity(self) -> Decimal:
        return (
            self.liabilities.total
            + self.equity.total
            + self.retained_earnings
            + self.current_period_net_income
        )

    @property
    def is_balanced(self) -> bool:
        """The fundamental accounting equation must hold: A = L + E."""
        diff = abs(self.assets.total - self.total_liabilities_and_equity)
        return diff <= Decimal("0.02")
