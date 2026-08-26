"""
Rule-based Chart of Accounts classifier — $0, no OpenAI embeddings.

Flow: clean description → match account_rules (DB) → else builtin seeds → Suspense 9999.
Passive learning: when user assigns a real CoA, persist a keyword rule.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.infrastructure.repositories.supabase_client import get_supabase_client

SUSPENSE_CODE = "9999"
SUSPENSE_NAME = "Gastos No Categorizados (Suspense)"

# Bootstrap seeds when tenant has no account_rules yet
DEFAULT_SEED_RULES: list[tuple[list[str], str, str]] = [
    (["rent", "lease", "landlord"], "6020", "Rent Expense"),
    (["electric", "utility", "utilities", "water", "fpl"], "6030", "Utilities"),
    (["office depot", "staples", "supplies"], "6040", "Office Supplies"),
    (
        [
            "uber",
            "lyft",
            "airline",
            "hotel",
            "marriott",
            "airbnb",
            "restaurant",
            "starbucks",
            "doordash",
            "grubhub",
        ],
        "6050",
        "Travel & Meals",
    ),
    (["ads", "advertis", "facebook ads", "google ads", "marketing", "highlevel"], "6060", "Marketing & Advertising"),
    (["legal", "attorney", "accountant", "cpa", "consult"], "6070", "Professional Services"),
    (["insurance", "geico", "state farm"], "6080", "Insurance"),
    (["repair", "maintenance", "hvac"], "6090", "Repairs & Maintenance"),
    (
        ["software", "saas", "aws", "vercel", "github", "microsoft", "adobe", "openai", "technology"],
        "6100",
        "Technology & Software",
    ),
    (["fee", "bank fee", "service charge", "overdraft"], "6110", "Bank Fees & Charges"),
    (["tax", "irs", "license", "permit"], "6130", "Taxes & Licenses"),
    (["salary", "payroll", "wage", "gusto", "adp"], "6010", "Salaries & Wages"),
    (["interest income", "dividend"], "4030", "Interest Income"),
    (["payment thank", "autopay", "online payment", "thank you"], "1010", "Cash and Cash Equivalents"),
    (["deposit", "wire in", "ach credit"], "1010", "Cash and Cash Equivalents"),
    (["costco", "walmart", "target", "amazon", "exxon", "shell", "chevron", "fuel"], "5010", "Cost of Goods Sold"),
    (
        ["owner draw", "owners draw", "personal", "retiro socio", "owner's draw", "draws"],
        "3030",
        "Owner's Draws / Retiros del Socio",
    ),
]


@dataclass
class CoAMatch:
    code: str
    name: str
    confidence: float
    matched_keyword: str | None = None
    source: str = "none"  # seed | learned | manual | builtin | suspense


def clean_description(raw: str) -> str:
    """Strip invoice refs, auth codes, noisy dates so keyword match works."""
    text = (raw or "").lower()
    # auth / ref / confirmation codes
    text = re.sub(r"\b(auth|ref|conf|confirmation|invoice|inv|trx|txn)[#:\s-]*[a-z0-9-]{4,}\b", " ", text)
    text = re.sub(r"\b\d{4,}[-*]?\d{2,}[-*]?\d*\b", " ", text)  # long numeric ids
    text = re.sub(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", " ", text)  # dates
    text = re.sub(r"[*#]+", " ", text)
    text = re.sub(r"[^a-z0-9\s&./]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_learn_keyword(description: str) -> str | None:
    """Pick a stable token/phrase from a cleaned description for passive learning."""
    cleaned = clean_description(description)
    if not cleaned:
        return None
    # Prefer multi-word vendor-ish tokens (2–3 words) if short enough
    words = [w for w in cleaned.split() if len(w) >= 3 and not w.isdigit()]
    stop = {
        "the",
        "and",
        "for",
        "from",
        "payment",
        "purchase",
        "debit",
        "credit",
        "card",
        "visa",
        "mastercard",
        "pos",
        "usd",
        "check",
    }
    words = [w for w in words if w not in stop]
    if not words:
        return None
    if len(words) >= 2:
        phrase = f"{words[0]} {words[1]}"
        if len(phrase) <= 40:
            return phrase
    return words[0][:40]


class RuleCoAClassifier:
    """Classify descriptions against tenant account_rules without paid embeddings."""

    def __init__(self) -> None:
        self._rules_cache: dict[str, list[dict[str, Any]]] = {}
        self._accounts_cache: dict[str, dict[str, str]] = {}

    def invalidate(self, tenant_id: uuid.UUID) -> None:
        key = str(tenant_id)
        self._rules_cache.pop(key, None)
        self._accounts_cache.pop(key, None)

    def _load_accounts(self, tenant_id: uuid.UUID) -> dict[str, str]:
        key = str(tenant_id)
        if key in self._accounts_cache:
            return self._accounts_cache[key]
        client = get_supabase_client()
        result = (
            client.table("chart_of_accounts")
            .select("code,name")
            .eq("tenant_id", key)
            .execute()
        )
        accounts = {str(r["code"]): str(r["name"]) for r in (result.data or [])}
        if SUSPENSE_CODE not in accounts:
            accounts[SUSPENSE_CODE] = SUSPENSE_NAME
        self._accounts_cache[key] = accounts
        return accounts

    def _load_rules(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        key = str(tenant_id)
        if key in self._rules_cache:
            return self._rules_cache[key]
        client = get_supabase_client()
        result = (
            client.table("account_rules")
            .select("id,keywords,account_code,account_name,source,hit_count,is_active")
            .eq("tenant_id", key)
            .eq("is_active", True)
            .execute()
        )
        rows = list(result.data or [])
        if not rows:
            rows = self.ensure_seed_rules(tenant_id)
        self._rules_cache[key] = rows
        return rows

    def ensure_seed_rules(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        """Insert DEFAULT_SEED_RULES if tenant has none. Returns loaded rows."""
        client = get_supabase_client()
        existing = (
            client.table("account_rules")
            .select("id")
            .eq("tenant_id", str(tenant_id))
            .limit(1)
            .execute()
        )
        if existing.data:
            result = (
                client.table("account_rules")
                .select("id,keywords,account_code,account_name,source,hit_count,is_active")
                .eq("tenant_id", str(tenant_id))
                .eq("is_active", True)
                .execute()
            )
            return list(result.data or [])

        accounts = self._load_accounts(tenant_id)
        payload = []
        for keywords, code, default_name in DEFAULT_SEED_RULES:
            payload.append(
                {
                    "tenant_id": str(tenant_id),
                    "keywords": [k.lower() for k in keywords],
                    "account_code": code,
                    "account_name": accounts.get(code, default_name),
                    "source": "seed",
                    "is_active": True,
                }
            )
        if payload:
            client.table("account_rules").insert(payload).execute()
        self.invalidate(tenant_id)
        result = (
            client.table("account_rules")
            .select("id,keywords,account_code,account_name,source,hit_count,is_active")
            .eq("tenant_id", str(tenant_id))
            .eq("is_active", True)
            .execute()
        )
        rows = list(result.data or [])
        self._rules_cache[str(tenant_id)] = rows
        return rows

    def classify(self, tenant_id: uuid.UUID, description: str) -> CoAMatch:
        cleaned = clean_description(description)
        accounts = self._load_accounts(tenant_id)
        rules = self._load_rules(tenant_id)

        best: CoAMatch | None = None
        for rule in rules:
            keywords = rule.get("keywords") or []
            if isinstance(keywords, str):
                keywords = [keywords]
            hits = [kw for kw in keywords if kw and str(kw).lower() in cleaned]
            if not hits:
                continue
            # Prefer longer keyword matches
            best_kw = max(hits, key=len)
            conf = min(0.55 + 0.08 * len(hits) + 0.02 * len(best_kw), 0.97)
            # Learned rules slightly preferred when equal
            if rule.get("source") == "learned":
                conf = min(conf + 0.03, 0.98)
            code = str(rule["account_code"])
            name = accounts.get(code) or str(rule.get("account_name") or code)
            candidate = CoAMatch(
                code=code,
                name=name,
                confidence=conf,
                matched_keyword=best_kw,
                source=str(rule.get("source") or "seed"),
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate

        if best:
            return best

        return CoAMatch(
            code=SUSPENSE_CODE,
            name=accounts.get(SUSPENSE_CODE, SUSPENSE_NAME),
            confidence=0.2,
            matched_keyword=None,
            source="suspense",
        )

    def learn_from_correction(
        self,
        tenant_id: uuid.UUID,
        description: str,
        account_code: str,
        account_name: str,
    ) -> dict[str, Any] | None:
        """Passive learning: store a keyword when user assigns a non-suspense account."""
        if not account_code or account_code == SUSPENSE_CODE:
            return None
        keyword = extract_learn_keyword(description)
        if not keyword:
            return None

        client = get_supabase_client()
        # Avoid duplicate keyword for same tenant+code
        existing = (
            client.table("account_rules")
            .select("id,keywords,hit_count")
            .eq("tenant_id", str(tenant_id))
            .eq("account_code", account_code)
            .eq("is_active", True)
            .execute()
        )
        for row in existing.data or []:
            kws = [str(k).lower() for k in (row.get("keywords") or [])]
            if keyword in kws:
                client.table("account_rules").update(
                    {
                        "hit_count": int(row.get("hit_count") or 0) + 1,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", row["id"]).execute()
                self.invalidate(tenant_id)
                return {"id": row["id"], "keyword": keyword, "updated": True}

        inserted = (
            client.table("account_rules")
            .insert(
                {
                    "tenant_id": str(tenant_id),
                    "keywords": [keyword],
                    "account_code": account_code,
                    "account_name": account_name or account_code,
                    "source": "learned",
                    "hit_count": 1,
                    "is_active": True,
                }
            )
            .execute()
        )
        self.invalidate(tenant_id)
        row = (inserted.data or [None])[0]
        return {"id": row.get("id") if row else None, "keyword": keyword, "created": True}

    def list_rules(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        client = get_supabase_client()
        result = (
            client.table("account_rules")
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .order("created_at", desc=True)
            .execute()
        )
        return list(result.data or [])
