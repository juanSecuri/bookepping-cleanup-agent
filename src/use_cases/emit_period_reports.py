"""
Build period financial statements from verified transactions (local/$0 path).

Emits:
  - P&L (Income Statement) — excludes equity (Owner's Draws / contributions)
  - Balance Sheet — Assets = Liabilities + Equity (incl. period net income)
  - Cash Flow — Operating / Investing / Financing (draws → financing)
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from src.domain.models.enums import TransactionStatus, TransactionType
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.transaction_repository import TransactionRepository

# Equity accounts that must never hit P&L
EQUITY_CODES = frozenset({"3010", "3020", "3030"})
OWNER_DRAWS_CODE = "3030"


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
        if period and len(period) == 7:
            date_from = f"{period}-01"
            y, m = int(period[:4]), int(period[5:7])
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
            lambda: {
                "inflows": Decimal("0"),
                "outflows": Decimal("0"),
                "financing_in": Decimal("0"),
                "financing_out": Decimal("0"),
            }
        )
        annual: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {
                "inflows": Decimal("0"),
                "outflows": Decimal("0"),
                "financing_in": Decimal("0"),
                "financing_out": Decimal("0"),
            }
        )

        financing_in = Decimal("0")
        financing_out = Decimal("0")
        operating_in = Decimal("0")
        operating_out = Decimal("0")

        for t in verified:
            code = t.chart_of_accounts_code or "9999"
            name = t.chart_of_accounts_name or "Uncategorized"
            acct_type = coa_types.get(code) or self._infer_type(t.transaction_type)
            month_key = str(t.transaction_date)[:7]
            year_key = str(t.transaction_date)[:4]
            is_equity = acct_type == "equity" or code in EQUITY_CODES

            cash = asset_map.setdefault(
                "1010",
                {
                    "code": "1010",
                    "name": "Cash and Cash Equivalents",
                    "amount": Decimal("0"),
                    "txCount": 0,
                },
            )

            if is_equity:
                # Owner contributions / draws → Patrimonio + Financing CF (not P&L)
                eq = equity_map.setdefault(
                    code,
                    {"code": code, "name": name, "amount": Decimal("0"), "txCount": 0},
                )
                if t.transaction_type == TransactionType.INCOME:
                    cash["amount"] += t.amount
                    cash["txCount"] += 1
                    eq["amount"] += t.amount  # contribution increases equity
                    eq["txCount"] += 1
                    financing_in += t.amount
                    monthly[month_key]["financing_in"] += t.amount
                    annual[year_key]["financing_in"] += t.amount
                else:
                    cash["amount"] -= t.amount
                    cash["txCount"] += 1
                    eq["amount"] -= t.amount  # draws reduce equity
                    eq["txCount"] += 1
                    financing_out += t.amount
                    monthly[month_key]["financing_out"] += t.amount
                    annual[year_key]["financing_out"] += t.amount
                continue

            if acct_type == "liability":
                li = liability_map.setdefault(
                    code, {"code": code, "name": name, "amount": Decimal("0"), "txCount": 0}
                )
                if t.transaction_type == TransactionType.INCOME:
                    # loan proceeds / liability increase with cash in
                    li["amount"] += t.amount
                    cash["amount"] += t.amount
                    financing_in += t.amount
                    monthly[month_key]["financing_in"] += t.amount
                    annual[year_key]["financing_in"] += t.amount
                else:
                    # liability payment
                    li["amount"] -= t.amount
                    cash["amount"] -= t.amount
                    financing_out += t.amount
                    monthly[month_key]["financing_out"] += t.amount
                    annual[year_key]["financing_out"] += t.amount
                li["txCount"] += 1
                cash["txCount"] += 1
                continue

            if t.transaction_type == TransactionType.INCOME:
                entry = revenue_map.setdefault(
                    code, {"code": code, "name": name, "amount": Decimal("0"), "txCount": 0}
                )
                entry["amount"] += t.amount
                entry["txCount"] += 1
                operating_in += t.amount
                monthly[month_key]["inflows"] += t.amount
                annual[year_key]["inflows"] += t.amount
                cash["amount"] += t.amount
                cash["txCount"] += 1
            else:
                entry = expense_map.setdefault(
                    code, {"code": code, "name": name, "amount": Decimal("0"), "txCount": 0}
                )
                entry["amount"] += t.amount
                entry["txCount"] += 1
                operating_out += t.amount
                monthly[month_key]["outflows"] += t.amount
                annual[year_key]["outflows"] += t.amount
                cash["amount"] -= t.amount
                cash["txCount"] += 1

        total_revenue = float(operating_in)
        total_expenses = float(operating_out)
        net_income = total_revenue - total_expenses

        assets = [
            {
                "code": v["code"],
                "name": v["name"],
                "amount": float(v["amount"]),
                "txCount": v["txCount"],
            }
            for v in asset_map.values()
        ]
        liabilities = [
            {
                "code": v["code"],
                "name": v["name"],
                "amount": float(v["amount"]),
                "txCount": v["txCount"],
            }
            for v in liability_map.values()
        ]
        equity_lines = [
            {
                "code": v["code"],
                "name": v["name"],
                "amount": float(v["amount"]),
                "txCount": v["txCount"],
            }
            for v in sorted(equity_map.values(), key=lambda x: x["code"])
            if v["code"] != "3020"
        ]
        # Utilidad / (pérdida) del ejercicio → Patrimonio (inyectada; no se pierde en P&L)
        prior_re = equity_map.get("3020")
        re_amount = float(prior_re["amount"]) if prior_re else 0.0
        equity_lines.append(
            {
                "code": "3020",
                "name": "Utilidad del ejercicio (Retained Earnings)",
                "amount": net_income + re_amount,
                "txCount": (prior_re["txCount"] if prior_re else 0) + len(verified),
            }
        )
        total_assets = sum(a["amount"] for a in assets)
        total_liabilities = sum(a["amount"] for a in liabilities)
        total_equity = sum(a["amount"] for a in equity_lines)
        imbalance = total_assets - (total_liabilities + total_equity)

        op_in_f = float(operating_in)
        op_out_f = float(operating_out)
        fin_in_f = float(financing_in)
        fin_out_f = float(financing_out)
        net_operating = op_in_f - op_out_f
        net_financing = fin_in_f - fin_out_f
        net_cash = net_operating + net_financing

        cf_monthly = [
            {
                "period": k,
                "inflows": float(v["inflows"]),
                "outflows": float(v["outflows"]),
                "financing_in": float(v["financing_in"]),
                "financing_out": float(v["financing_out"]),
                "net": float(
                    v["inflows"]
                    - v["outflows"]
                    + v["financing_in"]
                    - v["financing_out"]
                ),
            }
            for k, v in sorted(monthly.items())
        ]
        cf_annual = [
            {
                "period": k,
                "inflows": float(v["inflows"]),
                "outflows": float(v["outflows"]),
                "financing_in": float(v["financing_in"]),
                "financing_out": float(v["financing_out"]),
                "net": float(
                    v["inflows"]
                    - v["outflows"]
                    + v["financing_in"]
                    - v["financing_out"]
                ),
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
            "note": (
                "P&L excluye Owner's Draws / aportes a patrimonio "
                f"({OWNER_DRAWS_CODE} y cuentas equity)."
            ),
        }

        balance = {
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity_lines,
            "totalAssets": total_assets,
            "totalLiabilities": total_liabilities,
            "totalEquity": total_equity,
            "imbalance": imbalance,
            "balanced": abs(imbalance) < 0.02,
            "equation": "Assets = Liabilities + Equity (incl. utilidad del ejercicio)",
            "note": (
                "Balance desde txs verificadas: cash proxy; "
                "Owner's Draws reducen Patrimonio; "
                "utilidad neta del periodo se inyecta en 3020."
            ),
        }

        cash_flow = {
            "operating": {
                "inflows": op_in_f,
                "outflows": op_out_f,
                "net": net_operating,
            },
            "investing": {"inflows": 0.0, "outflows": 0.0, "net": 0.0},
            "financing": {
                "inflows": fin_in_f,
                "outflows": fin_out_f,
                "net": net_financing,
                "note": "Incluye Owner's Draws / aportes (equity) y movimientos de pasivo.",
            },
            "netChange": net_cash,
            "note": (
                "Cash flow O/I/F local/$0: operativo = P&L; "
                "financiación = equity draws/aportes + pasivos."
            ),
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
