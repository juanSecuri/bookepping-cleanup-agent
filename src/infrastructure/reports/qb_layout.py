"""
QuickBooks-style report layout (Profit and Loss / Balance Sheet).

Turns the engine's account lines into the same row structure QuickBooks Online prints:

    Income
      Parent account
        Sub-account ............ 100.00
      Total for Parent account   100.00
    Total Income                 100.00
    ...
    Net Income

The numbers always come from the platform (verified Drive / bank transactions).
The template Excel files only define *shape*: titles, section order, "Total for X" rows.

Rows are flat dicts so the web table and the Excel writer render the exact same thing:

    {"kind": "header" | "account" | "total" | "summary",
     "label": str, "depth": int, "amount": float | None, "byMonth": {...} | None,
     "code": str | None, "sumOf": [row indexes] (totals), "terms": [[sign, row index]] (summaries)}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

MONTH_KEYS = [f"{m:02d}" for m in range(1, 13)]
MONTH_NAMES = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

# CoA subcategories that only say *which section* an account belongs to.
# Anything else in `subcategory` is treated as a QuickBooks parent account.
_GENERIC_SUBCATEGORIES = frozenset(
    s.lower()
    for s in (
        "",
        "other",
        "operating revenue",
        "revenue",
        "income",
        "sales",
        "other income",
        "cogs",
        "cost of goods sold",
        "operating expenses",
        "expenses",
        "expense",
        "other expenses",
        "other expense",
        "suspense",
        "current assets",
        "fixed assets",
        "other assets",
        "current liabilities",
        "long-term liabilities",
        "long term liabilities",
        "equity",
    )
)

# Balance Sheet buckets, in QuickBooks order.
BANK = "Bank Accounts"
AR = "Accounts Receivable"
OTHER_CA = "Other Current Assets"
FIXED = "Fixed Assets"
OTHER_ASSETS = "Other Assets"
AP = "Accounts Payable"
CARDS = "Credit Cards"
OTHER_CL = "Other Current Liabilities"
LONG_TERM = "Long-term Liabilities"
_EXPLICIT_BUCKETS = {
    b.lower(): b for b in (BANK, AR, OTHER_CA, FIXED, OTHER_ASSETS, AP, CARDS, OTHER_CL, LONG_TERM)
}

_BANK_WORDS = (
    "bank",
    "checking",
    "savings",
    "cash",
    "money market",
    "chase",
    "bluevine",
    "relay",
    "ally",
)
_CARD_WORDS = (
    "credit card",
    "amex",
    "american express",
    "visa",
    "mastercard",
    "line of credit",
    "card",
)


# ── Tree ────────────────────────────────────────────────────────────────────


@dataclass
class _Node:
    label: str
    key: str = ""
    code: str | None = None
    amount: float | None = None
    by_month: dict[str, float] | None = None
    children: list[_Node] = field(default_factory=list)
    total_label: str | None = None  # set → this node is a section with a total row
    terms: list[tuple[int, str]] | None = None  # set → summary row (sign, section key)

    @property
    def is_section(self) -> bool:
        return self.total_label is not None


def _months(line: dict) -> dict[str, float]:
    raw = line.get("byMonth") or {}
    return {mk: float(raw.get(mk) or 0) for mk in MONTH_KEYS}


def _path_of(line: dict) -> list[str]:
    """Account path: QuickBooks ``Parent:Child:Grandchild`` names, else ``[subcategory, name]``
    when the subcategory is a real parent account (not a section bucket)."""
    name = str(line.get("name") or line.get("code") or "").strip()
    parts = [p.strip() for p in name.split(":") if p.strip()] or [name]
    if len(parts) > 1:
        return parts
    sub = str(line.get("subcategory") or "").strip()
    if sub and sub.lower() not in _GENERIC_SUBCATEGORIES and sub.lower() not in _EXPLICIT_BUCKETS:
        return [sub, name]
    return parts


def _account(line: dict, label: str, amount_key: str = "amount") -> _Node:
    return _Node(
        label=label,
        code=str(line.get("code") or "") or None,
        amount=float(line.get(amount_key) or 0),
        by_month=_months(line),
    )


@dataclass
class _Branch:
    lines: list[dict] = field(default_factory=list)  # postings on this exact account
    children: dict[str, _Branch] = field(default_factory=dict)


def _group(lines: list[dict], *, amount_key: str = "amount") -> list[_Node]:
    """Accounts in QuickBooks order: alphabetical, any depth of parent → sub-account."""
    root = _Branch()
    for line in lines:
        branch = root
        for part in _path_of(line):
            branch = branch.children.setdefault(part, _Branch())
        branch.lines.append(line)

    def build(branch: _Branch) -> list[_Node]:
        nodes: list[_Node] = []
        for label in sorted(branch.children, key=str.lower):
            child = branch.children[label]
            own = [_account(line, label, amount_key) for line in child.lines]
            if child.children:
                # Parent with its own postings: QuickBooks lists them first, under the parent.
                nodes.append(
                    _Node(
                        label=label,
                        children=own + build(child),
                        total_label=f"Total for {label}",
                    )
                )
            else:
                nodes.extend(own)
        return nodes

    return build(root)


def _section(key: str, label: str, children: list[_Node], total_label: str | None = None) -> _Node:
    return _Node(
        label=label, key=key, children=children, total_label=total_label or f"Total {label}"
    )


def _summary(key: str, label: str, terms: list[tuple[int, str]]) -> _Node:
    return _Node(label=label, key=key, terms=terms)


# ── Flatten (shared by web + Excel) ─────────────────────────────────────────


def _node_amount(node: _Node) -> tuple[float, dict[str, float]]:
    if node.children or node.is_section:
        total, months = 0.0, {mk: 0.0 for mk in MONTH_KEYS}
        for child in node.children:
            a, m = _node_amount(child)
            total += a
            for mk in MONTH_KEYS:
                months[mk] += m[mk]
        return total, months
    return float(node.amount or 0), dict(node.by_month or {mk: 0.0 for mk in MONTH_KEYS})


def flatten(nodes: list[_Node]) -> list[dict]:
    rows: list[dict] = []
    totals_by_key: dict[str, int] = {}

    def emit(node: _Node, depth: int) -> int:
        if node.terms is not None:
            amount, months = 0.0, {mk: 0.0 for mk in MONTH_KEYS}
            terms: list[list[int]] = []
            for sign, key in node.terms:
                if key not in totals_by_key:
                    continue
                ref = rows[totals_by_key[key]]
                amount += sign * ref["amount"]
                for mk in MONTH_KEYS:
                    months[mk] += sign * ref["byMonth"][mk]
                terms.append([sign, totals_by_key[key]])
            rows.append(
                {
                    "kind": "summary",
                    "label": node.label,
                    "depth": depth,
                    "amount": amount,
                    "byMonth": months,
                    "code": None,
                    "terms": terms,
                }
            )
            if node.key:
                totals_by_key[node.key] = len(rows) - 1
            return len(rows) - 1

        if node.is_section:
            rows.append(
                {
                    "kind": "header",
                    "label": node.label,
                    "depth": depth,
                    "amount": None,
                    "byMonth": None,
                    "code": None,
                }
            )
            child_refs = [emit(child, depth + 1) for child in node.children]
            amount, months = _node_amount(node)
            rows.append(
                {
                    "kind": "total",
                    "label": node.total_label,
                    "depth": depth,
                    "amount": amount,
                    "byMonth": months,
                    "code": None,
                    "sumOf": child_refs,
                }
            )
            if node.key:
                totals_by_key[node.key] = len(rows) - 1
            return len(rows) - 1

        amount, months = _node_amount(node)
        rows.append(
            {
                "kind": "account",
                "label": node.label,
                "depth": depth,
                "amount": amount,
                "byMonth": months,
                "code": node.code,
            }
        )
        return len(rows) - 1

    for n in nodes:
        emit(n, 0)
    return rows


# ── Profit and Loss ─────────────────────────────────────────────────────────


def _is_other(line: dict, word: str) -> bool:
    return str(line.get("subcategory") or "").strip().lower() in {f"other {word}", f"other {word}s"}


def build_pnl_rows(pnl: dict) -> list[dict]:
    revenue = pnl.get("revenueItems") or []
    cogs = pnl.get("cogsItems") or []
    expenses = pnl.get("expenseItems") or []
    income = [r for r in revenue if not _is_other(r, "income")]
    other_income = [r for r in revenue if _is_other(r, "income")]
    opex = [r for r in expenses if not _is_other(r, "expense")]
    other_expenses = [r for r in expenses if _is_other(r, "expense")]

    nodes: list[_Node] = [_section("income", "Income", _group(income))]
    if cogs:
        nodes.append(_section("cogs", "Cost of Goods Sold", _group(cogs)))
    nodes.append(_summary("gross", "Gross Profit", [(1, "income"), (-1, "cogs")]))
    nodes.append(_section("expenses", "Expenses", _group(opex)))
    nodes.append(_summary("noi", "Net Operating Income", [(1, "gross"), (-1, "expenses")]))
    if other_income or other_expenses:
        if other_income:
            nodes.append(_section("other_income", "Other Income", _group(other_income)))
        if other_expenses:
            nodes.append(_section("other_expenses", "Other Expenses", _group(other_expenses)))
        nodes.append(
            _summary("net_other", "Net Other Income", [(1, "other_income"), (-1, "other_expenses")])
        )
    nodes.append(_summary("net_income", "Net Income", [(1, "noi"), (1, "net_other")]))
    return flatten(nodes)


# ── Balance Sheet ───────────────────────────────────────────────────────────


def _asset_bucket(line: dict) -> str:
    sub = str(line.get("subcategory") or "").strip().lower()
    if sub in _EXPLICIT_BUCKETS:
        return _EXPLICIT_BUCKETS[sub]
    name = str(line.get("name") or "").lower()
    if "fixed" in sub or "depreciation" in name:
        return FIXED
    if sub and sub not in {"current assets", "other"} and "current" not in sub:
        return OTHER_ASSETS if "other" in sub else FIXED if "equipment" in sub else OTHER_CA
    if str(line.get("code") or "") == "1010" or any(w in name for w in _BANK_WORDS):
        return BANK
    if "receivable" in name:
        return AR
    return OTHER_CA


def _liability_bucket(line: dict) -> str:
    sub = str(line.get("subcategory") or "").strip().lower()
    if sub in _EXPLICIT_BUCKETS:
        return _EXPLICIT_BUCKETS[sub]
    if "long" in sub:
        return LONG_TERM
    name = str(line.get("name") or "").lower()
    if any(w in name for w in _CARD_WORDS):
        return CARDS
    if "accounts payable" in name or name.endswith("(a/p)"):
        return AP
    return OTHER_CL


def _buckets(lines: list[dict], classify, order: tuple[str, ...]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {b: [] for b in order}
    for line in lines:
        out.setdefault(classify(line), []).append(line)
    return out


def _bucket_sections(buckets: dict[str, list[dict]], names: tuple[str, ...]) -> list[_Node]:
    return [
        _section(f"bucket:{name}", name, _group(buckets[name], amount_key="closing"))
        for name in names
        if buckets.get(name)
    ]


def build_balance_rows(balance: dict) -> list[dict]:
    a = _buckets(
        balance.get("assets") or [], _asset_bucket, (BANK, AR, OTHER_CA, FIXED, OTHER_ASSETS)
    )
    li = _buckets(
        balance.get("liabilities") or [], _liability_bucket, (AP, CARDS, OTHER_CL, LONG_TERM)
    )

    current_assets = _bucket_sections(a, (BANK, AR, OTHER_CA))
    asset_nodes: list[_Node] = []
    if current_assets:
        asset_nodes.append(_section("current_assets", "Current Assets", current_assets))
    if a[FIXED]:
        asset_nodes.append(
            _section("fixed_assets", "Fixed Assets", _group(a[FIXED], amount_key="closing"))
        )
    if a[OTHER_ASSETS]:
        asset_nodes.append(
            _section("other_assets", "Other Assets", _group(a[OTHER_ASSETS], amount_key="closing"))
        )

    current_liabs = _bucket_sections(li, (AP, CARDS, OTHER_CL))
    liab_nodes: list[_Node] = []
    if current_liabs:
        liab_nodes.append(_section("current_liabilities", "Current Liabilities", current_liabs))
    if li[LONG_TERM]:
        liab_nodes.append(
            _section(
                "long_term", "Long-term Liabilities", _group(li[LONG_TERM], amount_key="closing")
            )
        )

    equity_lines = balance.get("equity") or []
    special = {"3020", "NI"}
    equity_nodes = _group(
        [e for e in equity_lines if str(e.get("code")) not in special], amount_key="closing"
    )
    # QuickBooks always closes Equity with Retained Earnings, then Net Income.
    for code in ("3020", "NI"):
        for e in equity_lines:
            if str(e.get("code")) == code:
                equity_nodes.append(_account(e, str(e.get("name") or code), "closing"))

    nodes = [
        _section("assets", "Assets", asset_nodes),
        _Node(
            label="Liabilities and Equity",
            key="liabilities_and_equity",
            total_label="Total Liabilities and Equity",
            children=[
                _section("liabilities", "Liabilities", liab_nodes),
                _section("equity", "Equity", equity_nodes),
            ],
        ),
    ]
    return flatten(nodes)


# ── Titles ──────────────────────────────────────────────────────────────────


def pnl_period_text(
    fiscal_year: str | None,
    month: int | None,
    date_from: str | None,
    date_to: str | None,
    granularity: str = "annual",
) -> str:
    if granularity == "range":
        return f"{_pretty_date(date_from)} - {_pretty_date(date_to)}"
    if fiscal_year and month:
        return f"{MONTH_NAMES[month - 1]} {fiscal_year}"
    if fiscal_year:
        return f"January-December, {fiscal_year}"
    return f"{_pretty_date(date_from)} - {_pretty_date(date_to)}"


def balance_as_of_text(as_of_date: str | None) -> str:
    return f"As of {_pretty_date(as_of_date)}"


def _pretty_date(iso: str | None) -> str:
    if not iso:
        return "…"
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


REPORT_TZ = "America/New_York"  # TPC clients are in Florida


def basis_footer(now: datetime | None = None) -> str:
    """QuickBooks footer, e.g. ``Cash Basis Friday, October 30, 2026 01:15 PM GMT-04:00``."""
    now = now or datetime.now(ZoneInfo(REPORT_TZ))
    offset = now.strftime("%z")
    gmt = f" GMT{offset[:3]}:{offset[3:]}" if offset else ""
    return (
        f"Cash Basis {now.strftime('%A, %B')} {now.day}, {now.year} {now.strftime('%I:%M %p')}{gmt}"
    )


def build_qb_reports(bundle, company_name: str) -> dict:
    """Payload for the web: both QuickBooks reports for one period."""
    balance = bundle.balance_sheet or {}
    return {
        "company": company_name,
        "basis": "Cash Basis",
        "fiscal_year": bundle.fiscal_year,
        "month": bundle.month,
        "transaction_count": bundle.transaction_count,
        "pending_count": bundle.pending_count,
        "profit_and_loss": {
            "title": "Profit and Loss",
            "period": pnl_period_text(
                bundle.fiscal_year,
                bundle.month,
                bundle.date_from,
                bundle.date_to,
                bundle.granularity,
            ),
            "rows": build_pnl_rows(bundle.pnl or {}),
        },
        "balance_sheet": {
            "title": "Balance Sheet",
            "period": balance_as_of_text(balance.get("asOfDate") or bundle.date_to),
            "rows": build_balance_rows(balance),
            "balanced": bool(balance.get("balanced")),
            "imbalance": float(balance.get("imbalance") or 0),
        },
    }
