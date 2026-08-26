"""Infer cash_flow_type: operating | investing | financing ($0 / deterministic)."""
from __future__ import annotations

EQUITY_CODES = frozenset({"3010", "3020", "3030"})
CASH_CODES = frozenset({"1010", "1020"})


def infer_cash_flow_type(
    *,
    account_code: str | None,
    account_type: str | None = None,
) -> str:
    code = (account_code or "").strip()
    acct = (account_type or "").strip().lower()
    if code in EQUITY_CODES or acct in {"equity", "liability"}:
        return "financing"
    if acct == "asset" and code not in CASH_CODES:
        return "investing"
    return "operating"
