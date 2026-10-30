"""
Build period financial statements from verified transactions (local/$0 path).

Emits:
  - P&L (Income Statement) for the period — excludes equity (Owner's Draws / contributions)
  - Balance Sheet *as of* the period end — cumulative since inception; prior years roll
    into Retained Earnings and the current year shows as Net Income (QuickBooks semantics)
  - Cash Flow for the period — Operating / Investing / Financing (draws → financing)
"""

from __future__ import annotations

import uuid
from calendar import monthrange
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from src.domain.models.enums import TransactionStatus, TransactionType
from src.infrastructure.classification.cash_flow import infer_cash_flow_type
from src.infrastructure.drive.year_policy import parse_max_fiscal_year
from src.infrastructure.reports.funding_accounts import (
    FundingAccount,
    build_funding_resolver,
    is_card_payment_memo,
)
from src.infrastructure.repositories.supabase_client import get_supabase_client
from src.infrastructure.repositories.transaction_repository import TransactionRepository
from src.infrastructure.repositories.workspace_repository import WorkspaceRepository

# Equity accounts that must never hit P&L
EQUITY_CODES = frozenset({"3010", "3020", "3030"})
OWNER_DRAWS_CODE = "3030"
COGS_CODES = frozenset({"5010", "5000", "5100", "5020"})
# 2010 is often used as CC payment / "thank you" clearing — not true vendor AP
TRANSFER_CLEARING_CODES = frozenset({"2010"})
MONTH_KEYS = [f"{m:02d}" for m in range(1, 13)]
NET_INCOME_CODE = "NI"  # virtual equity line (current-year P&L)


def resolve_account_type(code: str, coa_type: str | None, tx_type: TransactionType) -> str:
    """Prefer CoA / code family over bank transaction_type (OCR often flips income/expense)."""
    code = (code or "").strip()
    declared = (coa_type or "").strip().lower()
    if declared in {"asset", "liability", "equity", "income", "cogs", "expense"}:
        # Still override when code family contradicts (orphan / mis-seeded CoA)
        if code.startswith("4") and declared != "income":
            return "income"
        if code.startswith("5") and declared != "cogs":
            return "cogs"
        if (code.startswith("6") or code == "9999") and declared not in {"expense", "cogs"}:
            return "expense"
        if code.startswith("3") and declared != "equity":
            return "equity"
        if code.startswith("2") and declared != "liability":
            return "liability"
        if code.startswith("1") and declared != "asset":
            return "asset"
        return declared
    if code.startswith("4") or code in {"4010", "4020", "4030", "4040"}:
        return "income"
    if code.startswith("5") or code in COGS_CODES:
        return "cogs"
    if code.startswith("6") or code == "9999":
        return "expense"
    if code.startswith("3") or code in EQUITY_CODES:
        return "equity"
    if code.startswith("2"):
        return "liability"
    if code.startswith("1"):
        return "asset"
    return "income" if tx_type == TransactionType.INCOME else "expense"


def is_transfer_memo(description: str | None) -> bool:
    d = (description or "").lower()
    return any(
        m in d
        for m in (
            "thank you",
            "credit card pmt",
            "credit card payment",
            "automatic payment",
            "online credit card",
            "mobile to ****",
            "online to ****",
            "payment to ****",
            "account close out",
            "balance transfer",
        )
    )


def effective_cash_direction(
    acct_type: str,
    tx_type: TransactionType,
    *,
    description: str | None = None,
) -> TransactionType:
    """Bank feeds mis-tag expense merchants as income — trust account family for OpEx/COGS."""
    if acct_type in {"expense", "cogs"} and tx_type == TransactionType.INCOME:
        if not is_transfer_memo(description):
            return TransactionType.EXPENSE
    if acct_type == "income" and tx_type == TransactionType.EXPENSE:
        return TransactionType.INCOME
    return tx_type


# QuickBooks-like subcategory order within Balance Sheet major groups
ASSET_SUBCATEGORY_ORDER = ("Current Assets", "Fixed Assets")
LIABILITY_SUBCATEGORY_ORDER = ("Current Liabilities", "Long-Term Liabilities")
EQUITY_SUBCATEGORY_ORDER = ("Equity",)
BS_ACCOUNT_TYPES = frozenset({"asset", "liability", "equity"})


def _empty_months() -> dict[str, float]:
    return {k: 0.0 for k in MONTH_KEYS}


def cumulative_by_month(activity: dict[str, float]) -> dict[str, float]:
    """Running sum over MONTH_KEYS (QuickBooks-style YTD closing per month column)."""
    out = _empty_months()
    running = 0.0
    for mk in MONTH_KEYS:
        running += float(activity.get(mk) or 0)
        out[mk] = running
    return out


def _sum_stores_by_month(*stores: dict[str, dict]) -> dict[str, float]:
    out = _empty_months()
    for store in stores:
        for bucket in store.values():
            for mk, val in (bucket.get("byMonth") or {}).items():
                key = str(mk)[-2:] if len(str(mk)) >= 2 else str(mk)
                if key in out:
                    out[key] += float(val)
    return out


def _apply_cumulative_bs_line(line: dict) -> None:
    cum = cumulative_by_month(line.get("byMonth") or {})
    line["byMonth"] = cum
    line["closing"] = float(line.get("amount") or 0)


def _apply_cumulative_bs_lines(lines: list[dict]) -> None:
    for line in lines:
        _apply_cumulative_bs_line(line)


def _default_subcategory(account_type: str) -> str:
    if account_type == "asset":
        return "Current Assets"
    if account_type == "liability":
        return "Current Liabilities"
    if account_type == "equity":
        return "Equity"
    return "Other"


def _acct_bucket() -> dict:
    return {
        "code": "",
        "name": "",
        "amount": Decimal("0"),
        "txCount": 0,
        "byMonth": defaultdict(lambda: Decimal("0")),
        "debits": Decimal("0"),
        "credits": Decimal("0"),
        "subcategory": "",
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
        "subcategory": v.get("subcategory") or "",
    }
    if with_months:
        by_m = _empty_months()
        for mk, val in (v.get("byMonth") or {}).items():
            key = str(mk)[-2:] if len(str(mk)) >= 2 else str(mk)
            if key in by_m:
                by_m[key] = float(val)
        row["byMonth"] = by_m
    return row


def merge_coa_zero_balances(
    asset_map: dict[str, dict],
    liability_map: dict[str, dict],
    equity_map: dict[str, dict],
    coa: dict[str, dict],
) -> None:
    """Ensure every CoA asset/liability/equity account appears (zero if no activity)."""
    targets = {
        "asset": asset_map,
        "liability": liability_map,
        "equity": equity_map,
    }
    for code, meta in coa.items():
        acct_type = str(meta.get("account_type") or "").lower()
        if acct_type not in targets:
            continue
        store = targets[acct_type]
        sub = str(meta.get("subcategory") or "").strip() or _default_subcategory(acct_type)
        name = str(meta.get("name") or code)
        if code not in store:
            entry = _acct_bucket()
            entry["code"] = code
            entry["name"] = name
            entry["subcategory"] = sub
            store[code] = entry
        else:
            store[code]["subcategory"] = sub or store[code].get("subcategory") or ""
            if name and (not store[code].get("name") or store[code]["name"] == code):
                store[code]["name"] = name


def build_balance_sections(
    assets: list[dict],
    liabilities: list[dict],
    equity: list[dict],
) -> dict[str, list[dict]]:
    """Group BS lines by CoA subcategory (QuickBooks-style)."""

    def _group(lines: list[dict], preferred: tuple[str, ...]) -> list[dict]:
        buckets: dict[str, list[dict]] = defaultdict(list)
        for line in lines:
            sub = str(line.get("subcategory") or "").strip() or "Other"
            buckets[sub].append(line)
        ordered_keys: list[str] = []
        for key in preferred:
            if key in buckets:
                ordered_keys.append(key)
        for key in sorted(k for k in buckets if k not in preferred):
            ordered_keys.append(key)
        sections: list[dict] = []
        for key in ordered_keys:
            group_lines = sorted(buckets[key], key=lambda x: str(x.get("code") or ""))
            sections.append(
                {
                    "subcategory": key,
                    "lines": group_lines,
                    "total": sum(float(x.get("amount") or 0) for x in group_lines),
                }
            )
        return sections

    return {
        "assets": _group(assets, ASSET_SUBCATEGORY_ORDER),
        "liabilities": _group(liabilities, LIABILITY_SUBCATEGORY_ORDER),
        "equity": _group(equity, EQUITY_SUBCATEGORY_ORDER),
    }


def _bump(
    store: dict[str, dict],
    code: str,
    name: str,
    amount: Decimal,
    month_key: str,
    *,
    as_debit: bool | None = None,
    subcategory: str | None = None,
) -> None:
    entry = store.setdefault(code, _acct_bucket())
    entry["code"] = code
    entry["name"] = name or entry["name"] or code
    if subcategory and not entry.get("subcategory"):
        entry["subcategory"] = subcategory
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


def _cf_bucket() -> dict[str, Decimal]:
    return {
        "inflows": Decimal("0"),
        "outflows": Decimal("0"),
        "financing_in": Decimal("0"),
        "financing_out": Decimal("0"),
    }


@dataclass
class Ledger:
    """Postings by account family for one set of verified transactions."""

    revenue: dict[str, dict] = field(default_factory=dict)
    cogs: dict[str, dict] = field(default_factory=dict)
    expense: dict[str, dict] = field(default_factory=dict)
    asset: dict[str, dict] = field(default_factory=dict)
    liability: dict[str, dict] = field(default_factory=dict)
    equity: dict[str, dict] = field(default_factory=dict)
    cf_op: dict[str, dict] = field(default_factory=dict)
    cf_inv: dict[str, dict] = field(default_factory=dict)
    cf_fin: dict[str, dict] = field(default_factory=dict)
    monthly: dict[str, dict[str, Decimal]] = field(default_factory=lambda: defaultdict(_cf_bucket))
    annual: dict[str, dict[str, Decimal]] = field(default_factory=lambda: defaultdict(_cf_bucket))
    operating_in: Decimal = Decimal("0")
    operating_out: Decimal = Decimal("0")
    investing_in: Decimal = Decimal("0")
    investing_out: Decimal = Decimal("0")
    financing_in: Decimal = Decimal("0")
    financing_out: Decimal = Decimal("0")
    count: int = 0

    @property
    def net_income(self) -> Decimal:
        return self.operating_in - self.operating_out

    def net_income_by_month(self) -> dict[str, float]:
        rev = _sum_stores_by_month(self.revenue)
        cogs = _sum_stores_by_month(self.cogs)
        opex = _sum_stores_by_month(self.expense)
        return {mk: rev[mk] - cogs[mk] - opex[mk] for mk in MONTH_KEYS}


CLEARING_CODE = "2010-CLR"
CLEARING_NAME = "Card Payments & Transfers in Transit"


def _fund(
    led: Ledger,
    coa: dict[str, dict],
    account: FundingAccount | None,
    signed: Decimal,
    month_key: str,
) -> None:
    """Statement side of a posting. ``signed`` = +money in / −money out of that statement.

    Bank → asset goes up with money in. Card → liability goes *down* with a credit.
    Unknown statement → the CoA cash account (1010)."""
    if account is None:
        meta = coa.get("1010") or {}
        _bump(
            led.asset,
            "1010",
            str(meta.get("name") or "Cash and Cash Equivalents"),
            signed,
            month_key,
            as_debit=signed >= 0,
            subcategory=str(meta.get("subcategory") or "").strip() or "Current Assets",
        )
    elif account.kind == "card":
        _bump(
            led.liability,
            account.key,
            account.name,
            -signed,
            month_key,
            as_debit=signed >= 0,
            subcategory=account.subcategory,
        )
    else:
        _bump(
            led.asset,
            account.key,
            account.name,
            signed,
            month_key,
            as_debit=signed >= 0,
            subcategory=account.subcategory,
        )


def _clearing(led: Ledger, signed: Decimal, month_key: str) -> None:
    """Category side of transfers between the client's own statements (card payments,
    bank-to-bank). Nets to zero when both statements are loaded; what remains is a
    payment whose other statement is missing."""
    _bump(
        led.liability,
        CLEARING_CODE,
        CLEARING_NAME,
        signed,
        month_key,
        as_debit=signed < 0,
        subcategory="Other Current Liabilities",
    )


def _financing(
    led: Ledger, code: str, name: str, amount: Decimal, month_key: str, *, inflow: bool
) -> None:
    year_key = month_key[:4]
    if inflow:
        led.financing_in += amount
        led.monthly[month_key]["financing_in"] += amount
        led.annual[year_key]["financing_in"] += amount
        _bump(led.cf_fin, code, name, amount, month_key, as_debit=False)
    else:
        led.financing_out += amount
        led.monthly[month_key]["financing_out"] += amount
        led.annual[year_key]["financing_out"] += amount
        _bump(led.cf_fin, code, name, -amount, month_key, as_debit=True)


def post_transactions(
    transactions: list,
    coa: dict[str, dict],
    funding: Callable[[object], FundingAccount | None] | None = None,
) -> Ledger:
    """Route each verified transaction by CoA family (never by the bank's sign alone).

    P&L and Cash flow follow the CoA family. The Balance Sheet is double entry:
    statement side (bank / card / cash) + category side (P&L, equity, asset, loan or
    transfer), so Assets = Liabilities + Equity by construction."""
    led = Ledger()
    for t in transactions:
        led.count += 1
        code = t.chart_of_accounts_code or "9999"
        coa_meta = coa.get(code) or {}
        # QuickBooks shows the CoA name (may carry "Parent:Child" hierarchy).
        name = str(coa_meta.get("name") or "") or t.chart_of_accounts_name or "Uncategorized"
        acct_type = resolve_account_type(
            code, str(coa_meta.get("account_type") or ""), t.transaction_type
        )
        raw_sub = str(coa_meta.get("subcategory") or "").strip()
        bs_sub = raw_sub or _default_subcategory(acct_type if acct_type in BS_ACCOUNT_TYPES else "")
        description = getattr(t, "description", None)
        direction = effective_cash_direction(acct_type, t.transaction_type, description=description)
        inflow = direction == TransactionType.INCOME
        cf = t.cash_flow_type or infer_cash_flow_type(account_code=code, account_type=acct_type)
        month_key = str(t.transaction_date)[:7]
        year_key = month_key[:4]
        amount = t.amount
        account = funding(t) if funding else None
        signed = amount if inflow else -amount

        if acct_type == "equity" or code in EQUITY_CODES:
            _fund(led, coa, account, signed, month_key)
            _bump(
                led.equity,
                code,
                name,
                signed,
                month_key,
                as_debit=not inflow,
                subcategory=bs_sub or "Equity",
            )
            _financing(led, code, name, amount, month_key, inflow=inflow)
            continue

        # Card payments / own transfers: never P&L, never fake Accounts Payable.
        transfer_clearing = code in TRANSFER_CLEARING_CODES or (
            acct_type == "liability" and is_transfer_memo(description)
        )
        if transfer_clearing or code == "1010":
            if account is not None and account.kind == "card" and is_card_payment_memo(description):
                signed = amount  # a payment on a card statement is always a credit
            _fund(led, coa, account, signed, month_key)
            _clearing(led, signed, month_key)
            if code != "1010":
                _financing(led, code, name, amount, month_key, inflow=signed > 0)
            continue

        if acct_type == "liability" or cf == "financing":
            # Loan proceeds raise the liability; payments from the bank reduce it.
            _fund(led, coa, account, signed, month_key)
            if acct_type == "liability":
                _bump(
                    led.liability,
                    code,
                    name,
                    signed,
                    month_key,
                    as_debit=not inflow,
                    subcategory=bs_sub,
                )
            else:
                _clearing(led, signed, month_key)
            _financing(led, code, name, amount, month_key, inflow=inflow)
            continue

        if cf == "investing" or acct_type == "asset":
            _fund(led, coa, account, signed, month_key)
            if acct_type == "asset":
                _bump(
                    led.asset,
                    code,
                    name,
                    -signed,
                    month_key,
                    as_debit=not inflow,
                    subcategory=bs_sub,
                )
            else:
                _clearing(led, signed, month_key)
            if inflow:
                led.investing_in += amount
                _bump(led.cf_inv, code, name, amount, month_key, as_debit=False)
            else:
                led.investing_out += amount
                _bump(led.cf_inv, code, name, -amount, month_key, as_debit=True)
            continue

        # P&L: route ONLY by account family (4xxx income / 5xxx COGS / 6xxx expense)
        if acct_type == "income":
            _bump(led.revenue, code, name, amount, month_key, as_debit=False, subcategory=raw_sub)
            led.operating_in += amount
            led.monthly[month_key]["inflows"] += amount
            led.annual[year_key]["inflows"] += amount
            _fund(led, coa, account, amount, month_key)
            _bump(led.cf_op, code, name, amount, month_key, as_debit=False)
        else:
            is_cogs = acct_type == "cogs" or code in COGS_CODES
            target = led.cogs if is_cogs else led.expense
            _bump(target, code, name, amount, month_key, as_debit=True, subcategory=raw_sub)
            led.operating_out += amount
            led.monthly[month_key]["outflows"] += amount
            led.annual[year_key]["outflows"] += amount
            _fund(led, coa, account, -amount, month_key)
            _bump(led.cf_op, code, name, -amount, month_key, as_debit=True)
    return led


def _months_float(by_month: dict) -> dict[str, float]:
    out = _empty_months()
    for mk, val in (by_month or {}).items():
        key = str(mk)[-2:]
        if key in out:
            out[key] += float(val)
    return out


def _as_of_line(prior: dict | None, ytd: dict | None) -> dict:
    """Balance line as of a date: opening (all prior years) + YTD activity per month."""
    base = ytd or prior or {}
    opening = float(prior["amount"]) if prior else 0.0
    activity = _months_float(ytd["byMonth"]) if ytd else _empty_months()
    running = cumulative_by_month(activity)
    amount = opening + (float(ytd["amount"]) if ytd else 0.0)
    return {
        "code": base.get("code") or "",
        "name": base.get("name") or "",
        "amount": amount,
        "txCount": int((prior or {}).get("txCount") or 0) + int((ytd or {}).get("txCount") or 0),
        "debits": float((prior or {}).get("debits") or 0) + float((ytd or {}).get("debits") or 0),
        "credits": float((prior or {}).get("credits") or 0)
        + float((ytd or {}).get("credits") or 0),
        "opening": opening,
        "closing": amount,
        "subcategory": base.get("subcategory") or "",
        "byMonth": {mk: opening + running[mk] for mk in MONTH_KEYS},
    }


def _as_of_lines(prior: dict[str, dict], ytd: dict[str, dict], *, skip: set[str]) -> list[dict]:
    codes = sorted((set(prior) | set(ytd)) - skip)
    return [_as_of_line(prior.get(c), ytd.get(c)) for c in codes]


def build_balance_sheet(
    prior: Ledger,
    ytd: Ledger,
    coa: dict[str, dict],
    *,
    as_of_year: str,
    as_of_date: str,
) -> dict:
    """
    QuickBooks semantics: the Balance Sheet is cumulative "as of" a date.

    - Asset / liability / equity accounts = every verified posting up to the date.
    - Retained Earnings = net income of all years before ``as_of_year`` (+ direct 3020 postings).
    - Net Income = current-year P&L through the as-of date.
    """
    merge_coa_zero_balances(ytd.asset, ytd.liability, ytd.equity, coa)
    assets = _as_of_lines(prior.asset, ytd.asset, skip=set())
    liabilities = _as_of_lines(prior.liability, ytd.liability, skip=set())
    equity_lines = _as_of_lines(prior.equity, ytd.equity, skip={"3020"})

    equity_sub = str((coa.get("3020") or {}).get("subcategory") or "").strip() or "Equity"
    prior_re_direct = float((prior.equity.get("3020") or {}).get("amount") or 0)
    retained_opening = float(prior.net_income) + prior_re_direct
    re_line = _as_of_line(
        {"amount": Decimal(str(retained_opening)), "txCount": prior.count},
        ytd.equity.get("3020"),
    )
    re_line.update(
        {
            "code": "3020",
            "name": str((coa.get("3020") or {}).get("name") or "Retained Earnings"),
            "subcategory": equity_sub,
        }
    )
    net_income = float(ytd.net_income)
    ni_by_month = cumulative_by_month(ytd.net_income_by_month())
    ni_line = {
        "code": NET_INCOME_CODE,
        "name": "Net Income",
        "amount": net_income,
        "txCount": ytd.count,
        "debits": 0.0,
        "credits": 0.0,
        "opening": 0.0,
        "closing": net_income,
        "subcategory": equity_sub,
        "byMonth": ni_by_month,
    }
    equity_lines.extend([re_line, ni_line])

    total_assets = sum(a["amount"] for a in assets)
    total_liabilities = sum(a["amount"] for a in liabilities)
    total_equity = sum(a["amount"] for a in equity_lines)
    imbalance = total_assets - (total_liabilities + total_equity)
    return {
        "assets": assets,
        "liabilities": liabilities,
        "equity": equity_lines,
        "sections": build_balance_sections(assets, liabilities, equity_lines),
        "totalAssets": total_assets,
        "totalLiabilities": total_liabilities,
        "totalEquity": total_equity,
        "netIncome": net_income,
        "retainedEarnings": re_line["amount"],
        "priorRetainedEarnings": retained_opening,
        "imbalance": imbalance,
        "balanced": abs(imbalance) < 0.02,
        "asOfYear": as_of_year,
        "asOfDate": as_of_date,
        "equation": (
            f"A = P + E  ({total_assets:,.2f} = {total_liabilities:,.2f} + {total_equity:,.2f})"
        ),
        "note": (
            f"Balance acumulado al {as_of_date} desde txs verificadas del cliente (Drive). "
            "Cada banco / tarjeta sale de la carpeta Drive de su extracto. "
            "Años anteriores → Retained Earnings; año en curso → Net Income (como QuickBooks). "
            f"'{CLEARING_NAME}' = pagos entre cuentas propias cuyo otro extracto no está cargado. "
            "Saldos previos al primer extracto importado no están incluidos."
        ),
    }


def _lines_by_size(store: dict[str, dict]) -> list[dict]:
    return [_serialize_line(v) for v in sorted(store.values(), key=lambda x: -abs(x["amount"]))]


def build_pnl(led: Ledger, granularity: str) -> dict:
    total_revenue = float(led.operating_in)
    total_expenses = float(led.operating_out)
    total_cogs = float(sum(v["amount"] for v in led.cogs.values()))
    total_opex = float(sum(v["amount"] for v in led.expense.values()))
    net_income = float(led.net_income)
    revenue_m = _sum_stores_by_month(led.revenue)
    cogs_m = _sum_stores_by_month(led.cogs)
    return {
        "revenue": total_revenue,
        "expenses": total_expenses,
        "cogs": total_cogs,
        "operatingExpenses": total_opex,
        "net_income": net_income,
        "totalRevenue": total_revenue,
        "totalExpenses": total_expenses,
        "totalCogs": total_cogs,
        "netIncome": net_income,
        "grossProfit": total_revenue - total_cogs,
        "grossProfitByMonth": {mk: revenue_m[mk] - cogs_m[mk] for mk in MONTH_KEYS},
        "revenueItems": _lines_by_size(led.revenue),
        "cogsItems": _lines_by_size(led.cogs),
        "expenseItems": _lines_by_size(led.expense),
        "months": MONTH_KEYS,
        "granularity": granularity,
        "note": (
            "P&L desde movimientos verificados del cliente (Drive/bancos). "
            "INGRESOS = solo cuentas 4xxx; gastos 5xxx/6xxx nunca van a ingresos. "
            f"Excluye Owner's Draws / aportes ({OWNER_DRAWS_CODE} y equity)."
        ),
    }


def _cf_rows(store: dict[str, dict[str, Decimal]]) -> list[dict]:
    return [
        {
            "period": k,
            "inflows": float(v["inflows"]),
            "outflows": float(v["outflows"]),
            "financing_in": float(v["financing_in"]),
            "financing_out": float(v["financing_out"]),
            "net": float(v["inflows"] - v["outflows"] + v["financing_in"] - v["financing_out"]),
        }
        for k, v in sorted(store.items())
    ]


def build_cash_flow(led: Ledger) -> tuple[dict, dict]:
    net_operating = float(led.operating_in - led.operating_out)
    net_investing = float(led.investing_in - led.investing_out)
    net_financing = float(led.financing_in - led.financing_out)
    net_cash = net_operating + net_investing + net_financing
    summary = {
        "operating": {
            "inflows": float(led.operating_in),
            "outflows": float(led.operating_out),
            "net": net_operating,
        },
        "investing": {
            "inflows": float(led.investing_in),
            "outflows": float(led.investing_out),
            "net": net_investing,
        },
        "financing": {
            "inflows": float(led.financing_in),
            "outflows": float(led.financing_out),
            "net": net_financing,
            "note": "Incluye Owner's Draws / aportes (equity) y movimientos de pasivo.",
        },
        "netChange": net_cash,
        "note": (
            "Cash flow O/I/F vía cash_flow_type + CoA ($0). "
            "Operativo = P&L; financiación = equity/pasivo; inversión = activos no caja."
        ),
    }
    detail = {
        "operating": _lines_by_size(led.cf_op),
        "investing": _lines_by_size(led.cf_inv),
        "financing": _lines_by_size(led.cf_fin),
        "operatingSubtotal": net_operating,
        "investingSubtotal": net_investing,
        "financingSubtotal": net_financing,
        "netTotal": net_cash,
    }
    return summary, detail


def resolve_period(
    *,
    period: str | None,
    date_from: str | None,
    date_to: str | None,
    fiscal_year: str | None,
    month: int | None,
    ceiling: int | None,
) -> dict:
    """Normalise the requested window (respecting the workspace's max fiscal year)."""
    if ceiling is not None:
        requested: int | None = None
        for candidate in (fiscal_year, period, date_from):
            if candidate and len(str(candidate)) >= 4 and str(candidate)[:4].isdigit():
                requested = int(str(candidate)[:4])
                break
        if requested is not None and requested > ceiling:
            fiscal_year, month, period, date_from, date_to = str(ceiling), None, None, None, None

    if fiscal_year and str(fiscal_year).isdigit() and len(str(fiscal_year)) == 4:
        period = (
            f"{fiscal_year}-{int(month):02d}"
            if month and 1 <= int(month) <= 12
            else str(fiscal_year)
        )

    if period and len(period) == 7 and period[4] == "-":
        y, m = int(period[:4]), int(period[5:7])
        return {
            "date_from": f"{period}-01",
            "date_to": f"{y}-{m:02d}-{monthrange(y, m)[1]:02d}",
            "label": period,
            "granularity": "monthly",
            "year": period[:4],
            "month": m,
        }
    if period and len(period) == 4 and period.isdigit():
        return {
            "date_from": f"{period}-01-01",
            "date_to": f"{period}-12-31",
            "label": period,
            "granularity": "annual",
            "year": period,
            "month": None,
        }
    return {
        "date_from": date_from,
        "date_to": date_to,
        "label": f"{date_from or '…'} → {date_to or '…'}",
        "granularity": "range",
        "year": (date_from or date_to or "")[:4] or None,
        "month": None,
    }


_POSTED = (TransactionStatus.VERIFIED, TransactionStatus.CLOSED)


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
        try:
            ws = await WorkspaceRepository().get(workspace_id)
        except Exception:
            ws = None
        ceiling = parse_max_fiscal_year(getattr(ws, "max_fiscal_year", None) if ws else None)
        win = resolve_period(
            period=period,
            date_from=date_from,
            date_to=date_to,
            fiscal_year=fiscal_year,
            month=month,
            ceiling=ceiling,
        )
        start = (win["date_from"] or "")[:10]
        end = (win["date_to"] or "")[:10]
        as_of = end or date_cls.today().isoformat()
        year_start = f"{as_of[:4]}-01-01"
        # "Recent" covers the report period and the as-of year (YTD for the Balance Sheet).
        recent_from = min(start, year_start) if start else ""

        def day(t) -> str:
            return str(t.transaction_date)[:10]

        # Older history only feeds Balance Sheet opening balances / Retained Earnings.
        # Separate query so a long history can never truncate the period being reported.
        history: list = []
        if recent_from:
            cutoff = (date_cls.fromisoformat(recent_from) - timedelta(days=1)).isoformat()
            history = await self._transactions.list_by_tenant_date_range(
                workspace_id,
                date_from=None,
                date_to=cutoff,
                statuses=[s.value for s in _POSTED],
                limit=500000,
            )
            history = [t for t in history if day(t) < recent_from and t.status in _POSTED]
        recent = await self._transactions.list_by_tenant_date_range(
            workspace_id, date_from=recent_from or None, date_to=end or None, limit=50000
        )
        recent = [
            t
            for t in recent
            if (not recent_from or day(t) >= recent_from) and (not end or day(t) <= end)
        ]

        def in_period(t) -> bool:
            return (not start or day(t) >= start) and (not end or day(t) <= end)

        posted = [t for t in recent if t.status in _POSTED]
        period_txns = [t for t in posted if in_period(t)]
        pending_count = sum(
            1 for t in recent if t.status == TransactionStatus.PENDING_REVIEW and in_period(t)
        )

        coa = self._coa_accounts(str(workspace_id))
        funding = build_funding_resolver(
            self._statement_documents(str(workspace_id)), history + posted
        )
        period_ledger = post_transactions(period_txns, coa, funding)
        prior_ledger = post_transactions(
            history + [t for t in posted if day(t) < year_start], coa, funding
        )
        ytd_ledger = post_transactions(
            [t for t in posted if year_start <= day(t) <= as_of], coa, funding
        )

        cash_flow, cash_flow_detail = build_cash_flow(period_ledger)
        return PeriodFinancialBundle(
            workspace_id=str(workspace_id),
            period_label=win["label"],
            date_from=win["date_from"],
            date_to=win["date_to"],
            currency=currency,
            pnl=build_pnl(period_ledger, win["granularity"]),
            balance_sheet=build_balance_sheet(
                prior_ledger, ytd_ledger, coa, as_of_year=as_of[:4], as_of_date=as_of
            ),
            cash_flow=cash_flow,
            cash_flow_monthly=_cf_rows(period_ledger.monthly),
            cash_flow_annual=_cf_rows(period_ledger.annual),
            cash_flow_detail=cash_flow_detail,
            transaction_count=len(period_txns),
            pending_count=pending_count,
            fiscal_year=win["year"],
            month=win["month"],
            granularity=win["granularity"],
        )

    def _statement_documents(self, tenant_id: str) -> list[dict]:
        """Source documents (Drive folder + bank/account) → which statement each tx is from."""
        client = get_supabase_client()
        out: list[dict] = []
        page = 1000
        try:
            while True:
                rows = (
                    client.table("documents")
                    .select("id,drive_path,file_name,vendor,queue_payload")
                    .eq("workspace_id", tenant_id)
                    .range(len(out), len(out) + page - 1)
                    .execute()
                    .data
                    or []
                )
                out.extend(rows)
                if len(rows) < page:
                    return out
        except Exception:  # reports still render with a single cash account
            return out

    def _coa_accounts(self, tenant_id: str) -> dict[str, dict]:
        client = get_supabase_client()
        result = (
            client.table("chart_of_accounts")
            .select("code,name,account_type,subcategory")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        out: dict[str, dict] = {}
        for r in result.data or []:
            out[str(r["code"])] = {
                "name": str(r.get("name") or ""),
                "account_type": str(r.get("account_type") or ""),
                "subcategory": str(r.get("subcategory") or ""),
            }
        return out
