"""
GenerateFinancialStatements use-case.

Consumes one or more closed MonthlyLedgers and produces:
  1. IncomeStatement  (Estado de Resultados / P&L)
  2. BalanceSheet     (Balance General)

Can generate for:
  - A single month:  fiscal_periods=["2022-06"]
  - A full year:     fiscal_periods=["2022-01", ..., "2022-12"]
  - Any custom range of consecutive months
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from decimal import Decimal

from src.domain.exceptions import BookkeepingError
from src.domain.models.enums import AccountType
from src.domain.models.financial_statement import (
    BalanceSheet,
    BalanceSheetSection,
    IncomeStatement,
    StatementLineItem,
)
from src.domain.models.monthly_ledger import LedgerEntry, MonthlyLedger


class GenerateFinancialStatementsUseCase:
    """
    Build Income Statement and Balance Sheet from closed MonthlyLedgers.

    Usage (single month):
        use_case = GenerateFinancialStatementsUseCase()
        income_stmt, balance_sheet = use_case.execute(
            tenant_id=uuid.UUID("..."),
            ledgers=[june_ledger],
            period_label="2022-06",
        )

    Usage (full year):
        income_stmt, balance_sheet = use_case.execute(
            tenant_id=uuid.UUID("..."),
            ledgers=list_of_12_monthly_ledgers,
            period_label="2022 Año Completo",
            prior_retained_earnings=Decimal("50000"),
        )
    """

    def execute(
        self,
        tenant_id: uuid.UUID,
        ledgers: list[MonthlyLedger],
        period_label: str,
        currency: str = "USD",
        prior_retained_earnings: Decimal = Decimal("0"),
    ) -> tuple[IncomeStatement, BalanceSheet]:
        if not ledgers:
            raise BookkeepingError("At least one closed MonthlyLedger is required")

        unclosed = [l for l in ledgers if l.status != "closed"]
        if unclosed:
            periods = [l.fiscal_period for l in unclosed]
            raise BookkeepingError(
                f"Periods {periods} are not closed yet. "
                "Run ClosePeriodUseCase before generating statements."
            )

        # Merge all ledger entries across periods
        merged = self._merge_ledgers(ledgers)

        income_stmt = self._build_income_statement(
            tenant_id, merged, period_label, currency
        )
        balance_sheet = self._build_balance_sheet(
            tenant_id, merged, period_label, currency,
            prior_retained_earnings, income_stmt.net_income
        )
        return income_stmt, balance_sheet

    # ── Private helpers ───────────────────────────────────────────────────────

    def _merge_ledgers(self, ledgers: list[MonthlyLedger]) -> dict[str, LedgerEntry]:
        """Combine entries from multiple periods, summing by account_code."""
        merged: dict[str, dict] = defaultdict(lambda: {
            "account_name": "", "account_type": None,
            "total_debit": Decimal("0"), "total_credit": Decimal("0"),
            "transaction_count": 0,
        })
        for ledger in ledgers:
            for entry in ledger.entries:
                agg = merged[entry.account_code]
                agg["account_name"] = entry.account_name
                agg["account_type"] = entry.account_type
                agg["total_debit"] += entry.total_debit
                agg["total_credit"] += entry.total_credit
                agg["transaction_count"] += entry.transaction_count

        return {
            code: LedgerEntry(
                account_code=code,
                account_name=agg["account_name"],
                account_type=agg["account_type"],
                total_debit=agg["total_debit"],
                total_credit=agg["total_credit"],
                transaction_count=agg["transaction_count"],
            )
            for code, agg in sorted(merged.items())
        }

    def _build_income_statement(
        self,
        tenant_id: uuid.UUID,
        entries: dict[str, LedgerEntry],
        period_label: str,
        currency: str,
    ) -> IncomeStatement:
        revenue_lines, cogs_lines, expense_lines = [], [], []
        total_revenue = total_cogs = total_expenses = Decimal("0")

        for entry in entries.values():
            line = StatementLineItem(
                account_code=entry.account_code,
                account_name=entry.account_name,
                amount=entry.net_balance,
            )
            if entry.account_type == AccountType.INCOME:
                revenue_lines.append(line)
                total_revenue += entry.net_balance
            elif entry.account_type == AccountType.COST_OF_GOODS_SOLD:
                cogs_lines.append(line)
                total_cogs += entry.net_balance
            elif entry.account_type == AccountType.EXPENSE:
                expense_lines.append(line)
                total_expenses += entry.net_balance

        gross_profit = total_revenue - total_cogs
        net_income = gross_profit - total_expenses

        return IncomeStatement(
            tenant_id=tenant_id,
            period_label=period_label,
            currency=currency.upper(),
            revenue_lines=revenue_lines,
            total_revenue=total_revenue,
            cogs_lines=cogs_lines,
            total_cogs=total_cogs,
            gross_profit=gross_profit,
            expense_lines=expense_lines,
            total_expenses=total_expenses,
            net_income=net_income,
        )

    def _build_balance_sheet(
        self,
        tenant_id: uuid.UUID,
        entries: dict[str, LedgerEntry],
        period_label: str,
        currency: str,
        prior_retained_earnings: Decimal,
        current_net_income: Decimal,
    ) -> BalanceSheet:
        asset_lines, liability_lines, equity_lines = [], [], []
        total_assets = total_liabilities = total_equity = Decimal("0")

        for entry in entries.values():
            if entry.account_type not in (AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY):
                continue
            line = StatementLineItem(
                account_code=entry.account_code,
                account_name=entry.account_name,
                amount=entry.net_balance,
            )
            if entry.account_type == AccountType.ASSET:
                asset_lines.append(line)
                total_assets += entry.net_balance
            elif entry.account_type == AccountType.LIABILITY:
                liability_lines.append(line)
                total_liabilities += entry.net_balance
            else:
                equity_lines.append(line)
                total_equity += entry.net_balance

        return BalanceSheet(
            tenant_id=tenant_id,
            period_label=period_label,
            currency=currency.upper(),
            assets=BalanceSheetSection(lines=asset_lines, total=total_assets),
            liabilities=BalanceSheetSection(lines=liability_lines, total=total_liabilities),
            equity=BalanceSheetSection(lines=equity_lines, total=total_equity),
            retained_earnings=prior_retained_earnings,
            current_period_net_income=current_net_income,
        )

    def from_ledger(
        self,
        ledger: MonthlyLedger,
        company_name: str = "Empresa",
    ) -> tuple[IncomeStatement, BalanceSheet]:
        """
        Convenience wrapper: generate statements from a single closed ledger.
        Used by the /periods/{period}/report API endpoint.
        """
        return self.execute(
            tenant_id=ledger.tenant_id,
            ledgers=[ledger],
            period_label=f"{company_name} — {ledger.fiscal_period}",
            currency=ledger.currency,
        )
