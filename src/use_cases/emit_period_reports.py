"""
Build period financial statements from verified transactions (local/$0 path).

Emits:
  - P&L (Income Statement)
  - Balance Sheet (simplified from CoA types + retained earnings)
  - Cash Flow (operating proxy from income/expense by month or range)
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from src.domain.models.enums import TransactionStatus, TransactionType
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.transaction_repository import TransactionRepository


@dataclass
class ReportLine:
    code: str
    name: str
    amount: float
    tx_count: int = 0


@dataclass
class PeriodFinancialBundle:
    workspace_id: str
    period_label: str
    date_from: str | None
    date_to: str | None
    currency: str
    pnl: dict
    balance_sheet: dict
    cash_flow: dict
    cash_flow_monthly: list[dict] = field(default_factory=list)
    cash_flow_annual: list[dict] = field(default_factory=list)
    transaction_count: int = 0
    engine: str = "local_rules"


class EmitPeriodReportsUseCase:
    def __init__(self, transaction_repo: TransactionRepository | None = None) -> None:
        self._transactions = transaction_repo or TransactionRepository()

    async def execute(
        self,
        workspace_id: uuid.UUID,
        *,
        period: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        currency: str = "USD",
    ) -> PeriodFinancialBundle:
        # period like 2026-05 or 2026
        if period and len(period) == 7:
            date_from = f"{period}-01"
            # end of month approx
            y, m = int(period[:4]), int(period[5:7])
            if m == 12:
                date_to = f"{y}-12-31"
            else:
                date_to = f"{y}-{m+1:02d}-01"
                # exclusive end handled as <= last day: use day 0 of next month via date math
                from calendar import monthrange

                date_to = f"{y}-{m:02d}-{monthrange(y, m)[1]:02d}"
            label = period
        elif period and len(period) == 4:
            date_from = f"{period}-01-01"
            date_to = f"{period}-12-31"
            label = f"{period} annual"
        else:
            label = f"{date_from or '…'} → {date_to or '…'}"

        txns = await self._transactions.list_by_tenant(workspace_id, limit=20000)
        verified = [t for t in txns if t.status == TransactionStatus.VERIFIED]
        if date_from:
            verified = [t for t in verified if str(t.transaction_date) >= date_from]
        if date_to:
            verified = [t for t in verified if str(t.transaction_date) <= date_to]

        coa_types = self._coa_types(str(workspace_id))

        revenue_map: dict[str, dict] = {}
        expense_map: dict[str, dict] = {}
        asset_map: dict[str, dict] = {}
        liability_map: dict[str, dict] = {}
        equity_map: dict[str, dict] = {}

        monthly: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {"inflows": Decimal("0"), "outflows": Decimal("0")}
        )
        annual: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {"inflows": Decimal("0"), "outflows": Decimal("0")}
        )

        for t in verified:
            code = t.chart_of_accounts_code or "9999"
            name = t.chart_of_accounts_name or "Uncategorized"
            acct_type = coa_types.get(code) or self._infer_type(t.transaction_type)
            month_key = str(t.transaction_date)[:7]
            year_key = str(t.transaction_date)[:4]

            if t.transaction_type == TransactionType.INCOME:
                entry = revenue_map.setdefault(
                    code, {"code": code, "name": name, "amount": Decimal("0"), "txCount": 0}
                )
                entry["amount"] += t.amount
                entry["txCount"] += 1
                monthly[month_key]["inflows"] += t.amount
                annual[year_key]["inflows"] += t.amount
                # cash proxy
                cash = asset_map.setdefault(
                    "1010",
                    {"code": "1010", "name": "Cash and Cash Equivalents", "amount": Decimal("0"), "txCount": 0},
                )
                cash["amount"] += t.amount
                cash["txCount"] += 1
            else:
                entry = expense_map.setdefault(
                    code, {"code": code, "name": name, "amount": Decimal("0"), "txCount": 0}
                )
                entry["amount"] += t.amount
                entry["txCount"] += 1
                monthly[month_key]["outflows"] += t.amount
                annual[year_key]["outflows"] += t.amount
                cash = asset_map.setdefault(
                    "1010",
                    {"code": "1010", "name": "Cash and Cash Equivalents", "amount": Decimal("0"), "txCount": 0},
                )
                cash["amount"] -= t.amount
                cash["txCount"] += 1

            if acct_type == "liability":
                li = liability_map.setdefault(
                    code, {"code": code, "name": name, "amount": Decimal("0"), "txCount": 0}
                )
                li["amount"] += t.amount
                li["txCount"] += 1
            elif acct_type == "equity":
                eq = equity_map.setdefault(
                    code, {"code": code, "name": name, "amount": Decimal("0"), "txCount": 0}
                )
                eq["amount"] += t.amount
                eq["txCount"] += 1

        total_revenue = float(sum(v["amount"] for v in revenue_map.values()))
        total_expenses = float(sum(v["amount"] for v in expense_map.values()))
        net_income = total_revenue - total_expenses

        assets = [
            {"code": v["code"], "name": v["name"], "amount": float(v["amount"]), "txCount": v["txCount"]}
            for v in asset_map.values()
        ]
        liabilities = [
            {"code": v["code"], "name": v["name"], "amount": float(v["amount"]), "txCount": v["txCount"]}
            for v in liability_map.values()
        ]
        equity_lines = [
            {"code": v["code"], "name": v["name"], "amount": float(v["amount"]), "txCount": v["txCount"]}
            for v in equity_map.values()
        ]
        equity_lines.append(
            {
                "code": "3020",
                "name": "Retained Earnings (period net)",
                "amount": net_income,
                "txCount": len(verified),
            }
        )
        total_assets = sum(a["amount"] for a in assets)
        total_liabilities = sum(a["amount"] for a in liabilities)
        total_equity = sum(a["amount"] for a in equity_lines)

        operating_in = total_revenue
        operating_out = total_expenses
        net_cash = operating_in - operating_out

        cf_monthly = [
            {
                "period": k,
                "inflows": float(v["inflows"]),
                "outflows": float(v["outflows"]),
                "net": float(v["inflows"] - v["outflows"]),
            }
            for k, v in sorted(monthly.items())
        ]
        cf_annual = [
            {
                "period": k,
                "inflows": float(v["inflows"]),
                "outflows": float(v["outflows"]),
                "net": float(v["inflows"] - v["outflows"]),
            }
            for k, v in sorted(annual.items())
        ]

        pnl = {
            "revenue": total_revenue,
            "expenses": total_expenses,
            "net_income": net_income,
            "totalRevenue": total_revenue,
            "totalExpenses": total_expenses,
            "netIncome": net_income,
            "revenueItems": [
                {
                    "code": v["code"],
                    "name": v["name"],
                    "amount": float(v["amount"]),
                    "txCount": v["txCount"],
                }
                for v in sorted(revenue_map.values(), key=lambda x: -x["amount"])
            ],
            "expenseItems": [
                {
                    "code": v["code"],
                    "name": v["name"],
                    "amount": float(v["amount"]),
                    "txCount": v["txCount"],
                }
                for v in sorted(expense_map.values(), key=lambda x: -x["amount"])
            ],
        }

        balance = {
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity_lines,
            "totalAssets": total_assets,
            "totalLiabilities": total_liabilities,
            "totalEquity": total_equity,
            "balanced": abs(total_assets - (total_liabilities + total_equity)) < 0.02
            or abs(total_assets - total_equity) < 0.02,
            "note": (
                "Balance simplificado desde transacciones verificadas + CoA "
                "(cash proxy). Doble partida completa llega con cierre de periodo."
            ),
        }

        cash_flow = {
            "operating": {
                "inflows": operating_in,
                "outflows": operating_out,
                "net": net_cash,
            },
            "investing": {"inflows": 0.0, "outflows": 0.0, "net": 0.0},
            "financing": {"inflows": 0.0, "outflows": 0.0, "net": 0.0},
            "netChange": net_cash,
            "note": "Cash flow operativo derivado de ingresos/gastos verificados (local/$0).",
        }

        return PeriodFinancialBundle(
            workspace_id=str(workspace_id),
            period_label=label,
            date_from=date_from,
            date_to=date_to,
            currency=currency,
            pnl=pnl,
            balance_sheet=balance,
            cash_flow=cash_flow,
            cash_flow_monthly=cf_monthly,
            cash_flow_annual=cf_annual,
            transaction_count=len(verified),
        )

    def _coa_types(self, tenant_id: str) -> dict[str, str]:
        client = get_supabase_client()
        result = (
            client.table("chart_of_accounts")
            .select("code,account_type")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return {str(r["code"]): str(r["account_type"]) for r in (result.data or [])}

    def _infer_type(self, tx_type: TransactionType) -> str:
        if tx_type == TransactionType.INCOME:
            return "income"
        return "expense"
