"""
Fiscal year close — roll P&L net into Retained Earnings (3020).

Does not invent cash journals: P&L resets naturally by date filter each year.
This persists the permanent carry so next year's Balance includes prior RE.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.domain.exceptions import BookkeepingError
from src.domain.models.enums import TransactionStatus, TransactionType
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.transaction_repository import TransactionRepository

TABLE = "fiscal_year_closes"
EQUITY_CODES = frozenset({"3010", "3020", "3030"})


class FiscalYearAlreadyClosedError(BookkeepingError):
    pass


@dataclass
class FiscalYearCloseResult:
    fiscal_year: str
    status: str
    total_revenue: float
    total_expenses: float
    net_income: float
    equity_draws_net: float
    transaction_count: int
    prior_retained_earnings: float
    retained_earnings_after: float
    row: dict[str, Any]


class FiscalYearCloseRepository:
    def get(self, tenant_id: uuid.UUID, fiscal_year: str) -> dict[str, Any] | None:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("fiscal_year", fiscal_year)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_closed(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("status", "closed")
            .order("fiscal_year", desc=True)
            .execute()
        )
        return list(result.data or [])

    def list_all(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .order("fiscal_year", desc=True)
            .execute()
        )
        return list(result.data or [])

    def upsert(self, row: dict[str, Any]) -> dict[str, Any]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .upsert(row, on_conflict="tenant_id,fiscal_year")
            .execute()
        )
        return (result.data or [row])[0]

    def sum_prior_retained(self, tenant_id: uuid.UUID, before_year: str) -> Decimal:
        """Sum net_income of closed years strictly before before_year (YYYY)."""
        total = Decimal("0")
        for row in self.list_closed(tenant_id):
            y = str(row.get("fiscal_year") or "")
            if y and y < before_year:
                total += Decimal(str(row.get("net_income") or 0))
        return total


class CloseFiscalYearUseCase:
    def __init__(
        self,
        transaction_repo: TransactionRepository | None = None,
        year_repo: FiscalYearCloseRepository | None = None,
    ) -> None:
        self._transactions = transaction_repo or TransactionRepository()
        self._years = year_repo or FiscalYearCloseRepository()

    async def execute(
        self,
        tenant_id: uuid.UUID,
        fiscal_year: str,
        *,
        currency: str = "USD",
        notes: str | None = None,
        allow_suspense: bool = False,
    ) -> FiscalYearCloseResult:
        if not re.match(r"^\d{4}$", fiscal_year):
            raise BookkeepingError("fiscal_year must be YYYY")

        existing = self._years.get(tenant_id, fiscal_year)
        if existing and existing.get("status") == "closed":
            raise FiscalYearAlreadyClosedError(
                f"Fiscal year {fiscal_year} is already closed."
            )

        all_txns = await self._transactions.list_by_tenant(tenant_id, limit=20000)
        year_txns = [
            t
            for t in all_txns
            if str(t.transaction_date)[:4] == fiscal_year
            and t.status
            in (TransactionStatus.VERIFIED, TransactionStatus.CLOSED)
        ]
        pending = [
            t
            for t in all_txns
            if str(t.transaction_date)[:4] == fiscal_year
            and t.status == TransactionStatus.PENDING_REVIEW
        ]
        if pending:
            raise BookkeepingError(
                f"Hay {len(pending)} transacciones pendientes de revisión en {fiscal_year}. "
                "Verifícalas antes del cierre anual."
            )
        if not year_txns:
            raise BookkeepingError(
                f"No hay transacciones verificadas en {fiscal_year} para cerrar."
            )

        suspense = [
            t
            for t in year_txns
            if (t.chart_of_accounts_code or "9999") == "9999"
        ]
        if suspense and not allow_suspense:
            raise BookkeepingError(
                f"Hay {len(suspense)} txs en Suspense (9999) en {fiscal_year}. "
                "Clasifícalas o cierra con allow_suspense=true."
            )

        coa_types = self._coa_types(str(tenant_id))
        revenue = Decimal("0")
        expenses = Decimal("0")
        draws_net = Decimal("0")

        for t in year_txns:
            code = t.chart_of_accounts_code or "9999"
            acct_type = coa_types.get(code) or (
                "income" if t.transaction_type == TransactionType.INCOME else "expense"
            )
            is_equity = acct_type == "equity" or code in EQUITY_CODES
            if is_equity:
                if t.transaction_type == TransactionType.INCOME:
                    draws_net -= t.amount  # contribution increases equity (negative draw)
                else:
                    draws_net += t.amount  # draw
                continue
            if acct_type == "liability":
                continue
            if t.transaction_type == TransactionType.INCOME:
                revenue += t.amount
            else:
                expenses += t.amount

        net_income = revenue - expenses
        prior = self._years.sum_prior_retained(tenant_id, fiscal_year)
        after = prior + net_income

        now = datetime.now(timezone.utc).isoformat()
        row = {
            "tenant_id": str(tenant_id),
            "fiscal_year": fiscal_year,
            "currency": currency.upper(),
            "total_revenue": float(revenue),
            "total_expenses": float(expenses),
            "net_income": float(net_income),
            "equity_draws_net": float(draws_net),
            "transaction_count": len(year_txns),
            "status": "closed",
            "notes": notes
            or (
                f"Cierre {fiscal_year}: P&L → Retained Earnings 3020. "
                f"NI={net_income}. Suspense={len(suspense)}."
            ),
            "closed_at": now,
            "reopened_at": None,
            "updated_at": now,
        }
        saved = self._years.upsert(row)

        # Mark year txs CLOSED (period = December of that year as fiscal tag)
        close_tag = f"{fiscal_year}-12"
        for t in year_txns:
            if t.status != TransactionStatus.CLOSED:
                await self._transactions.save(t.mark_closed(close_tag))

        return FiscalYearCloseResult(
            fiscal_year=fiscal_year,
            status="closed",
            total_revenue=float(revenue),
            total_expenses=float(expenses),
            net_income=float(net_income),
            equity_draws_net=float(draws_net),
            transaction_count=len(year_txns),
            prior_retained_earnings=float(prior),
            retained_earnings_after=float(after),
            row=saved,
        )

    async def reopen(
        self,
        tenant_id: uuid.UUID,
        fiscal_year: str,
    ) -> dict[str, Any]:
        existing = self._years.get(tenant_id, fiscal_year)
        if not existing or existing.get("status") != "closed":
            raise BookkeepingError(f"Fiscal year {fiscal_year} is not closed.")
        now = datetime.now(timezone.utc).isoformat()
        row = {
            **existing,
            "status": "reopened",
            "reopened_at": now,
            "updated_at": now,
            "notes": (existing.get("notes") or "") + " | Reabierto.",
        }
        return self._years.upsert(row)

    def _coa_types(self, tenant_id: str) -> dict[str, str]:
        client = get_supabase_client()
        result = (
            client.table("chart_of_accounts")
            .select("code,account_type")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return {str(r["code"]): str(r["account_type"]) for r in (result.data or [])}
