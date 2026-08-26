"""
Bank statement period balances + cadenazo (opening = prior closing).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from src.infrastructure.repositories.supabase_client import get_supabase_client

TABLE = "statement_periods"

_OPENING_RE = re.compile(
    r"(?:beginning|opening|previous|prior)\s+(?:balance|bal\.?)[:\s]*\$?\s*\(?([\d,]+\.?\d*)\)?",
    re.IGNORECASE,
)
_CLOSING_RE = re.compile(
    r"(?:ending|closing|new|current)\s+(?:balance|bal\.?)[:\s]*\$?\s*\(?([\d,]+\.?\d*)\)?",
    re.IGNORECASE,
)


def _parse_money(raw: str) -> Decimal | None:
    try:
        cleaned = raw.replace(",", "").strip()
        if not cleaned:
            return None
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def extract_statement_balances(text: str) -> tuple[Decimal | None, Decimal | None]:
    """Return (opening, closing) from statement OCR/text when present."""
    opening: Decimal | None = None
    closing: Decimal | None = None
    for m in _OPENING_RE.finditer(text or ""):
        opening = _parse_money(m.group(1)) or opening
    for m in _CLOSING_RE.finditer(text or ""):
        closing = _parse_money(m.group(1)) or closing
    return opening, closing


def prior_month(yyyy_mm: str) -> str | None:
    if not re.match(r"^\d{4}-\d{2}$", yyyy_mm):
        return None
    y, m = int(yyyy_mm[:4]), int(yyyy_mm[5:7])
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


@dataclass
class ChainResult:
    chain_ok: bool | None
    paused: bool
    delta: Decimal | None
    prior_closing: Decimal | None
    alert_message: str | None
    row: dict[str, Any]


class StatementPeriodRepository:
    def get(
        self,
        tenant_id: uuid.UUID,
        bank_account_number: str,
        statement_month: str,
    ) -> dict[str, Any] | None:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .eq("bank_account_number", bank_account_number)
            .eq("statement_month", statement_month)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_alerts(self, tenant_id: uuid.UUID, *, limit: int = 50) -> list[dict[str, Any]]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .or_("chain_ok.eq.false,paused.eq.true")
            .order("statement_month", desc=True)
            .limit(limit)
            .execute()
        )
        return list(result.data or [])

    def list_by_tenant(self, tenant_id: uuid.UUID, *, limit: int = 120) -> list[dict[str, Any]]:
        client = get_supabase_client()
        result = (
            client.table(TABLE)
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .order("statement_month", desc=True)
            .limit(limit)
            .execute()
        )
        return list(result.data or [])

    def upsert_and_validate(
        self,
        *,
        tenant_id: uuid.UUID,
        bank_name: str,
        bank_account_number: str,
        statement_month: str,
        opening_balance: Decimal | None,
        closing_balance: Decimal | None,
        movement_count: int = 0,
        source_document_id: uuid.UUID | None = None,
        tolerance: Decimal = Decimal("0.01"),
    ) -> ChainResult:
        """Save period balances and check cadenazo vs prior month closing."""
        client = get_supabase_client()
        prior = prior_month(statement_month)
        prior_closing: Decimal | None = None
        if prior:
            prev = self.get(tenant_id, bank_account_number, prior)
            if prev and prev.get("closing_balance") is not None:
                prior_closing = Decimal(str(prev["closing_balance"]))

        chain_ok: bool | None = None
        delta: Decimal | None = None
        alert: str | None = None
        paused = False

        if opening_balance is not None and prior_closing is not None:
            delta = opening_balance - prior_closing
            chain_ok = abs(delta) <= tolerance
            if not chain_ok:
                paused = True
                alert = (
                    f"Cadenazo roto: saldo final {prior} ({prior_closing}) ≠ "
                    f"≠ saldo inicial {statement_month} ({opening_balance}). "
                    f"Δ={delta}. Revisa el extracto antes de continuar el periodo."
                )
        elif opening_balance is not None and prior and prior_closing is None:
            chain_ok = None
            alert = (
                f"Sin cierre previo para {prior} (cuenta …{bank_account_number[-4:]}). "
                f"Importa el mes anterior para validar el cadenazo."
            )

        now = datetime.now(timezone.utc).isoformat()
        row = {
            "tenant_id": str(tenant_id),
            "bank_name": bank_name,
            "bank_account_number": bank_account_number,
            "statement_month": statement_month,
            "opening_balance": float(opening_balance) if opening_balance is not None else None,
            "closing_balance": float(closing_balance) if closing_balance is not None else None,
            "prior_closing": float(prior_closing) if prior_closing is not None else None,
            "chain_delta": float(delta) if delta is not None else None,
            "chain_ok": chain_ok,
            "paused": paused,
            "alert_message": alert,
            "movement_count": movement_count,
            "source_document_id": str(source_document_id) if source_document_id else None,
            "updated_at": now,
        }
        result = (
            client.table(TABLE)
            .upsert(row, on_conflict="tenant_id,bank_account_number,statement_month")
            .execute()
        )
        saved = (result.data or [row])[0]
        return ChainResult(
            chain_ok=chain_ok,
            paused=paused,
            delta=delta,
            prior_closing=prior_closing,
            alert_message=alert,
            row=saved,
        )


def acknowledge_chain(tenant_id: uuid.UUID, statement_month: str, bank_account_number: str) -> dict[str, Any]:
    """Clear pause flag after user acknowledges a chain break (continues processing)."""
    client = get_supabase_client()
    result = (
        client.table(TABLE)
        .update(
            {
                "paused": False,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "alert_message": "Cadenazo marcado como revisado por el usuario.",
            }
        )
        .eq("tenant_id", str(tenant_id))
        .eq("statement_month", statement_month)
        .eq("bank_account_number", bank_account_number)
        .execute()
    )
    return (result.data or [{}])[0]
