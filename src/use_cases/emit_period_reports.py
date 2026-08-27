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
from src.infrastructure.classification.cash_flow import infer_cash_flow_type
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.transaction_repository import TransactionRepository

# Equity accounts that must never hit P&L
EQUITY_CODES = frozenset({"3010", "3020", "3030"})
OWNER_DRAWS_CODE = "3030"
COGS_CODES = frozenset({"5010", "5000", "5100"})
MONTH_KEYS = [f"{m:02d}" for m in range(1, 13)]


def _empty_months() -> dict[str, float]:
    return {k: 0.0 for k in MONTH_KEYS}


def _acct_bucket() -> dict:
    return {
        "code": "",
        "name": "",
        "amount": Decimal("0"),
        "txCount": 0,
        "byMonth": defaultdict(lambda: Decimal("0")),
        "debits": Decimal("0"),
        "credits": Decimal("0"),
    }


def _serialize_line(v: dict, *, with_months: bool = True) -> dict:
    row = {
        "code": v["code"],
        "name": v["name"],
        "amount": float(v["amount"]),
        "txCount": int(v["txCount"]),
        "debits": float(v.get("debits") or 0),
        "credits": float(v.get("credits") or 0),
        "opening": 0.0,
        "closing": float(v["amount"]),
    }
    if with_months:
        by_m = _empty_months()
        for mk, val in (v.get("byMonth") or {}).items():
            key = str(mk)[-2:] if len(str(mk)) >= 2 else str(mk)
            if key in by_m:
                by_m[key] = float(val)
        row["byMonth"] = by_m
    return row


def _bump(
    store: dict[str, dict],
    code: str,
    name: str,
    amount: Decimal,
    month_key: str,
    *,
    as_debit: bool | None = None,
) -> None:
    entry = store.setdefault(code, _acct_bucket())
    entry["code"] = code
    entry["name"] = name or entry["name"] or code
    entry["amount"] += amount
    entry["txCount"] += 1
    month_num = month_key[5:7] if len(month_key) >= 7 else month_key
    entry["byMonth"][month_num] += amount
    if as_debit is True:
        entry["debits"] += amount
    elif as_debit is False:
        entry["credits"] += amount


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
    cash_flow_detail: dict = field(default_factory=dict)
    transaction_count: int = 0
    pending_count: int = 0
    fiscal_year: str | None = None
    month: int | None = None
    granularity: str = "range"  # annual | monthly | range
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
        fiscal_year: str | None = None,
        month: int | None = None,
        currency: str = "USD",
    ) -> PeriodFinancialBundle:
        # Prefer explicit fiscal_year (+ optional month) over free-text period
        if fiscal_year and str(fiscal_year).isdigit() and len(str(fiscal_year)) == 4:
            fy = str(fiscal_year)
            if month and 1 <= int(month) <= 12:
                period = f"{fy}-{int(month):02d}"
            else:
                period = fy

        granularity = "range"
        resolved_month: int | None = None
        resolved_year: str | None = None

        if period and len(period) == 7 and period[4] == "-":
            date_from = f"{period}-01"
            y, m = int(period[:4]), int(period[5:7])
            from calendar import monthrange

            date_to = f"{y}-{m:02d}-{monthrange(y, m)[1]:02d}"
            label = period
            granularity = "monthly"
            resolved_year = period[:4]
            resolved_month = m
        elif period and len(period) == 4 and period.isdigit():
            date_from = f"{period}-01-01"
            date_to = f"{period}-12-31"
            label = f"{period} annual"
            granularity = "annual"
            resolved_year = period
        else:
            label = f"{date_from or '…'} → {date_to or '…'}"
            if date_from and len(date_from) >= 4:
                resolved_year = date_from[:4]

        # Prefer SQL date window so years like 2024 are not dropped by
        # PostgREST's ~1000-row page cap when ordering newest-first.
        if date_from or date_to:
            period_txns = await self._transactions.list_by_tenant_date_range(
                workspace_id,
                date_from=date_from,
                date_to=date_to,
                limit=50000,
            )
            all_for_pending = period_txns
            verified = [
                t
                for t in period_txns
                if t.status in (TransactionStatus.VERIFIED, TransactionStatus.CLOSED)
            ]
        else:
            all_for_pending = await self._transactions.list_by_tenant(
                workspace_id, limit=50000
            )
            verified = [
                t
                for t in all_for_pending
                if t.status in (TransactionStatus.VERIFIED, TransactionStatus.CLOSED)
            ]

        def _tx_day(t) -> str:
            return str(t.transaction_date)[:10]

        pending_in_period = [
            t
            for t in all_for_pending
            if t.status == TransactionStatus.PENDING_REVIEW
            and (not date_from or _tx_day(t) >= date_from[:10])
            and (not date_to or _tx_day(t) <= date_to[:10])
        ]
        pending_count = len(pending_in_period)

        coa_types = self._coa_types(str(workspace_id))
        as_of_year = self._as_of_year(period, date_to, date_from)
        prior_re = self._prior_retained_earnings(str(workspace_id), as_of_year)

        revenue_map: dict[str, dict] = {}
        cogs_map: dict[str, dict] = {}
        expense_map: dict[str, dict] = {}
        asset_map: dict[str, dict] = {}
        liability_map: dict[str, dict] = {}
        equity_map: dict[str, dict] = {}
        cf_op_map: dict[str, dict] = {}
        cf_inv_map: dict[str, dict] = {}
        cf_fin_map: dict[str, dict] = {}

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
        investing_in = Decimal("0")
        investing_out = Decimal("0")
        operating_in = Decimal("0")
        operating_out = Decimal("0")

        for t in verified:
            code = t.chart_of_accounts_code or "9999"
            name = t.chart_of_accounts_name or "Uncategorized"
            acct_type = coa_types.get(code) or self._infer_type(t.transaction_type)
            cf = t.cash_flow_type or infer_cash_flow_type(
                account_code=code, account_type=acct_type
            )
            month_key = str(t.transaction_date)[:7]
            year_key = str(t.transaction_date)[:4]
            is_equity = acct_type == "equity" or code in EQUITY_CODES
            is_cogs = acct_type == "cogs" or code in COGS_CODES

            if "1010" not in asset_map:
                cash0 = _acct_bucket()
                cash0["code"] = "1010"
                cash0["name"] = "Cash and Cash Equivalents"
                asset_map["1010"] = cash0
            cash = asset_map["1010"]

            if is_equity:
                if t.transaction_type == TransactionType.INCOME:
                    cash["amount"] += t.amount
                    cash["txCount"] += 1
                    cash["debits"] += t.amount
                    cash["byMonth"][month_key[5:7]] += t.amount
                    _bump(equity_map, code, name, t.amount, month_key, as_debit=False)
                    financing_in += t.amount
                    monthly[month_key]["financing_in"] += t.amount
                    annual[year_key]["financing_in"] += t.amount
                    _bump(cf_fin_map, code, name, t.amount, month_key, as_debit=False)
                else:
                    cash["amount"] -= t.amount
                    cash["txCount"] += 1
                    cash["credits"] += t.amount
                    cash["byMonth"][month_key[5:7]] -= t.amount
                    _bump(equity_map, code, name, -t.amount, month_key, as_debit=True)
                    financing_out += t.amount
                    monthly[month_key]["financing_out"] += t.amount
                    annual[year_key]["financing_out"] += t.amount
                    _bump(cf_fin_map, code, name, -t.amount, month_key, as_debit=True)
                continue

            if acct_type == "liability" or cf == "financing":
                if t.transaction_type == TransactionType.INCOME:
                    if acct_type == "liability":
                        _bump(liability_map, code, name, t.amount, month_key, as_debit=False)
                    cash["amount"] += t.amount
                    cash["txCount"] += 1
                    cash["debits"] += t.amount
                    cash["byMonth"][month_key[5:7]] += t.amount
                    financing_in += t.amount
                    monthly[month_key]["financing_in"] += t.amount
                    annual[year_key]["financing_in"] += t.amount
                    _bump(cf_fin_map, code, name, t.amount, month_key, as_debit=False)
                else:
                    if acct_type == "liability":
                        _bump(liability_map, code, name, -t.amount, month_key, as_debit=True)
                    cash["amount"] -= t.amount
                    cash["txCount"] += 1
                    cash["credits"] += t.amount
                    cash["byMonth"][month_key[5:7]] -= t.amount
                    financing_out += t.amount
                    monthly[month_key]["financing_out"] += t.amount
                    annual[year_key]["financing_out"] += t.amount
                    _bump(cf_fin_map, code, name, -t.amount, month_key, as_debit=True)
                continue

            if cf == "investing":
                if t.transaction_type == TransactionType.INCOME:
                    cash["amount"] += t.amount
                    cash["debits"] += t.amount
                    investing_in += t.amount
                    _bump(cf_inv_map, code, name, t.amount, month_key, as_debit=False)
                else:
                    cash["amount"] -= t.amount
                    cash["credits"] += t.amount
                    investing_out += t.amount
                    _bump(cf_inv_map, code, name, -t.amount, month_key, as_debit=True)
                cash["txCount"] += 1
                cash["byMonth"][month_key[5:7]] += (
                    t.amount if t.transaction_type == TransactionType.INCOME else -t.amount
                )
                continue

            if t.transaction_type == TransactionType.INCOME:
                _bump(revenue_map, code, name, t.amount, month_key, as_debit=False)
                operating_in += t.amount
                monthly[month_key]["inflows"] += t.amount
                annual[year_key]["inflows"] += t.amount
                cash["amount"] += t.amount
                cash["txCount"] += 1
                cash["debits"] += t.amount
                cash["byMonth"][month_key[5:7]] += t.amount
                _bump(cf_op_map, code, name, t.amount, month_key, as_debit=False)
            else:
                target = cogs_map if is_cogs else expense_map
                _bump(target, code, name, t.amount, month_key, as_debit=True)
                operating_out += t.amount
                monthly[month_key]["outflows"] += t.amount
                annual[year_key]["outflows"] += t.amount
                cash["amount"] -= t.amount
                cash["txCount"] += 1
                cash["credits"] += t.amount
                cash["byMonth"][month_key[5:7]] -= t.amount
                _bump(cf_op_map, code, name, -t.amount, month_key, as_debit=True)

        total_revenue = float(operating_in)
        total_cogs = float(sum(v["amount"] for v in cogs_map.values()))
        total_opex = float(sum(v["amount"] for v in expense_map.values()))
        total_expenses = float(operating_out)
        net_income = total_revenue - total_expenses

        assets = [_serialize_line(v) for v in asset_map.values()]
        liabilities = [_serialize_line(v) for v in liability_map.values()]
        equity_lines = [
            _serialize_line(v)
            for v in sorted(equity_map.values(), key=lambda x: x["code"])
            if v["code"] != "3020"
        ]
        prior_re_row = equity_map.get("3020")
        re_tx_amount = float(prior_re_row["amount"]) if prior_re_row else 0.0
        if prior_re != 0:
            equity_lines.append(
                {
                    "code": "3020-PY",
                    "name": f"Utilidades retenidas (años cerrados antes de {as_of_year})",
                    "amount": float(prior_re),
                    "txCount": 0,
                    "debits": 0.0,
                    "credits": 0.0,
                    "opening": float(prior_re),
                    "closing": float(prior_re),
                    "byMonth": _empty_months(),
                }
            )
        equity_lines.append(
            {
                "code": "3020",
                "name": "Utilidad del ejercicio (Retained Earnings)",
                "amount": net_income + re_tx_amount,
                "txCount": (prior_re_row["txCount"] if prior_re_row else 0) + len(verified),
                "debits": 0.0,
                "credits": 0.0,
                "opening": 0.0,
                "closing": net_income + re_tx_amount,
                "byMonth": _empty_months(),
            }
        )
        total_assets = sum(a["amount"] for a in assets)
        total_liabilities = sum(a["amount"] for a in liabilities)
        total_equity = sum(a["amount"] for a in equity_lines)
        equity_for_equation = sum(
            a["amount"] for a in equity_lines if a["code"] != "3020-PY"
        )
        imbalance = total_assets - (total_liabilities + equity_for_equation)

        op_in_f = float(operating_in)
        op_out_f = float(operating_out)
        fin_in_f = float(financing_in)
        fin_out_f = float(financing_out)
        inv_in_f = float(investing_in)
        inv_out_f = float(investing_out)
        net_operating = op_in_f - op_out_f
        net_financing = fin_in_f - fin_out_f
        net_investing = inv_in_f - inv_out_f
        net_cash = net_operating + net_financing + net_investing

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

        def _lines_sorted(store: dict[str, dict]) -> list[dict]:
            return [
                _serialize_line(v)
                for v in sorted(store.values(), key=lambda x: -abs(x["amount"]))
            ]

        pnl = {
            "revenue": total_revenue,
            "expenses": total_expenses,
            "cogs": total_cogs,
            "operatingExpenses": total_opex,
            "net_income": net_income,
            "totalRevenue": total_revenue,
            "totalExpenses": total_expenses,
            "totalCogs": total_cogs,
            "netIncome": net_income,
            "revenueItems": _lines_sorted(revenue_map),
            "cogsItems": _lines_sorted(cogs_map),
            "expenseItems": _lines_sorted(expense_map),
            "months": MONTH_KEYS,
            "granularity": granularity,
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
            "priorRetainedEarnings": float(prior_re),
            "asOfYear": as_of_year,
            "equation": (
                f"A = P + E  ({total_assets:,.2f} = {total_liabilities:,.2f} + {equity_for_equation:,.2f})"
            ),
            "note": (
                "Balance desde txs verificadas/cerradas: cash proxy del periodo; "
                "Owner's Draws reducen Patrimonio; utilidad del periodo en 3020; "
                "RE de años cerrados en 3020-PY (no entra al cuadre del periodo)."
            ),
        }

        cash_flow = {
            "operating": {
                "inflows": op_in_f,
                "outflows": op_out_f,
                "net": net_operating,
            },
            "investing": {
                "inflows": inv_in_f,
                "outflows": inv_out_f,
                "net": net_investing,
            },
            "financing": {
                "inflows": fin_in_f,
                "outflows": fin_out_f,
                "net": net_financing,
                "note": "Incluye Owner's Draws / aportes (equity) y movimientos de pasivo.",
            },
            "netChange": net_cash,
            "note": (
                "Cash flow O/I/F vía cash_flow_type + CoA ($0). "
                "Operativo = P&L; financiación = equity/pasivo; inversión = activos no caja."
            ),
        }

        cash_flow_detail = {
            "operating": _lines_sorted(cf_op_map),
            "investing": _lines_sorted(cf_inv_map),
            "financing": _lines_sorted(cf_fin_map),
            "operatingSubtotal": net_operating,
            "investingSubtotal": net_investing,
            "financingSubtotal": net_financing,
            "netTotal": net_cash,
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
            cash_flow_detail=cash_flow_detail,
            transaction_count=len(verified),
            pending_count=pending_count,
            fiscal_year=resolved_year,
            month=resolved_month,
            granularity=granularity,
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

    @staticmethod
    def _as_of_year(
        period: str | None,
        date_to: str | None,
        date_from: str | None,
    ) -> str:
        if period and len(period) >= 4 and period[:4].isdigit():
            return period[:4]
        if date_to and len(date_to) >= 4 and date_to[:4].isdigit():
            return date_to[:4]
        if date_from and len(date_from) >= 4 and date_from[:4].isdigit():
            return date_from[:4]
        from datetime import date as date_cls

        return str(date_cls.today().year)

    def _prior_retained_earnings(self, tenant_id: str, as_of_year: str) -> Decimal:
        from src.use_cases.close_fiscal_year import FiscalYearCloseRepository

        return FiscalYearCloseRepository().sum_prior_retained(
            uuid.UUID(tenant_id), as_of_year
        )
