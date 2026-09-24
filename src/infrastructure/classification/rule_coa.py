"""
Rule-based Chart of Accounts classifier — $0, no OpenAI embeddings.

Flow: clean description → match account_rules (DB) → else builtin seeds → Suspense 9999
(or income default 4040 when direction=income).

Passive learning: when user assigns a real CoA, persist a keyword rule.
Direction-aware: credits/income prefer revenue accounts; debits/expenses prefer expense/COGS.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from src.infrastructure.repositories.supabase_client import get_supabase_client

SUSPENSE_CODE = "9999"
SUSPENSE_NAME = "Gastos No Categorizados (Suspense)"
INCOME_DEFAULT_CODE = "4040"
INCOME_DEFAULT_NAME = "Other Income"
SALES_REVENUE_CODE = "4010"
SERVICE_REVENUE_CODE = "4020"

Direction = Literal["income", "expense"]

INCOME_CODES = frozenset({"4010", "4020", "4030", "4040"})
# Codes that must not swallow operating revenue when direction=income
BLOCK_FOR_INCOME = frozenset({"1010", "9999"})

# Known expense merchants — credits mislabeled as income must not land on 4040
_EXPENSE_MERCHANT_HINTS: tuple[str, ...] = (
    "restaurant",
    "starbucks",
    "doordash",
    "grubhub",
    "texas roadhouse",
    "roadhouse",
    "sabor",
    "rodizio",
    "pizza",
    "cafe",
    "cafeteria",
    "meals",
    "food",
    "exxon",
    "shell",
    "chevron",
    "fuel",
    "7-eleven",
    "7 eleven",
    "wawa",
    "bp",
    "gas station",
    "parking",
    "toll",
    "sunpass",
    "google ads",
    "google *ads",
    "facebook ads",
    "meta ads",
    "instagram ads",
    "tiktok ads",
    "social media",
    "insurance",
    "geico",
    "state farm",
    "spa",
    "massage",
    "dental",
    "pharmacy",
    "cvs",
    "walgreens",
    "serenity spa",
    "barnes",
    "chamber",
)


def looks_like_expense_merchant(cleaned: str) -> bool:
    """True when description looks like OpEx/COGS vendor, not operating revenue."""
    if not cleaned:
        return False
    return any(hint in cleaned for hint in _EXPENSE_MERCHANT_HINTS)


# Bootstrap seeds when tenant has no account_rules yet
DEFAULT_SEED_RULES: list[tuple[list[str], str, str]] = [
    (["rent", "lease", "landlord"], "6020", "Rent Expense"),
    (["electric", "utility", "utilities", "water", "fpl"], "6030", "Utilities"),
    (["office depot", "staples", "supplies"], "6040", "Office Supplies"),
    (
        [
            "restaurant",
            "starbucks",
            "doordash",
            "grubhub",
            "texas roadhouse",
            "roadhouse",
            "sabor",
            "rodizio",
            "pizza",
            "cafe",
            "cafeteria",
            "meals",
            "food",
        ],
        "6050",
        "Meals Expense",
    ),
    (
        ["uber", "lyft", "airline", "hotel", "marriott", "airbnb"],
        "6055",
        "Travel",
    ),
    (["marketing", "highlevel", "advertis"], "6060", "Marketing & Advertising"),
    (
        [
            "google ads",
            "google *ads",
            "google",
            "facebook ads",
            "facebook",
            "meta ads",
            "instagram ads",
            "tiktok ads",
            "social media",
        ],
        "6065",
        "Social Media Ads",
    ),
    (
        ["legal", "attorney", "accountant", "cpa", "consult", "chamber"],
        "6070",
        "Professional Services",
    ),
    (["insurance", "geico", "state farm"], "6080", "Insurance"),
    (["repair", "maintenance", "hvac"], "6090", "Repairs & Maintenance"),
    (
        ["software", "saas", "aws", "vercel", "github", "microsoft", "adobe", "openai", "technology"],
        "6100",
        "Technology & Software",
    ),
    (
        [
            "fee",
            "bank fee",
            "service charge",
            "overdraft",
            "credit card interest",
            "interest charge",
            "finance charge",
        ],
        "6110",
        "Bank Fees & Charges",
    ),
    (["loan interest"], "6140", "Interest Expense"),
    (
        ["exxon", "shell", "chevron", "fuel", "7-eleven", "7 eleven", "wawa", "bp", "gas station"],
        "6160",
        "Gas & Oil",
    ),
    (["parking", "toll", "sunpass"], "6170", "Parking & Tolls"),
    (["tax", "irs", "license", "permit"], "6130", "Taxes & Licenses"),
    (["salary", "payroll", "wage", "gusto", "adp"], "6010", "Salaries & Wages"),
    (["interest income", "dividend", "interest earned"], "4030", "Interest Income"),
    # Customer / operating revenue (credits) — never Cash 1010
    (
        [
            "payment received",
            "customer payment",
            "client payment",
            "invoice payment",
            "payment thank",
            "thank you",
            "stripe",
            "square",
            "paypal",
            "zelle from",
            "venmo from",
            "sales",
            "revenue",
            "pos sale",
        ],
        "4010",
        "Sales Revenue",
    ),
    (
        ["service fee income", "consulting income", "professional fee", "retainer"],
        "4020",
        "Service Revenue",
    ),
    (
        ["deposit", "wire in", "wire credit", "ach credit", "incoming wire", "mobile deposit", "remote deposit"],
        "4040",
        "Other Income",
    ),
    (["costco", "walmart", "target", "amazon"], "5010", "Cost of Goods Sold"),
    (
        [
            "owner draw",
            "owners draw",
            "personal",
            "retiro socio",
            "owner's draw",
            "draws",
            "spa",
            "massage",
            "dental",
            "pharmacy",
            "cvs",
            "walgreens",
            "serenity spa",
        ],
        "3030",
        "Owner's Distributions / Equity Distributions",
    ),
]

FUEL_COGS_MARKERS = frozenset(
    {"exxon", "shell", "chevron", "fuel", "7-eleven", "7 eleven", "wawa", "bp", "gas station"}
)
SOCIAL_ADS_MARKERS = frozenset(
    {
        "google ads",
        "google *ads",
        "google",
        "facebook ads",
        "facebook",
        "meta ads",
        "instagram ads",
        "tiktok ads",
        "social media",
    }
)
TRAVEL_MARKERS = frozenset({"uber", "lyft", "airline", "hotel", "marriott", "airbnb"})
MEALS_MARKERS = frozenset(
    {
        "restaurant",
        "starbucks",
        "doordash",
        "grubhub",
        "texas roadhouse",
        "roadhouse",
        "sabor",
        "rodizio",
        "pizza",
        "cafe",
        "cafeteria",
        "meals",
        "food",
    }
)


@dataclass
class CoAMatch:
    code: str
    name: str
    confidence: float
    matched_keyword: str | None = None
    source: str = "none"  # seed | learned | manual | builtin | suspense | income_default
    vendor: str | None = None


def clean_description(raw: str) -> str:
    """Strip invoice refs, auth codes, noisy dates so keyword match works."""
    text = (raw or "").lower()
    text = re.sub(r"\b(auth|ref|conf|confirmation|invoice|inv|trx|txn)[#:\s-]*[a-z0-9-]{4,}\b", " ", text)
    text = re.sub(r"\b\d{4,}[-*]?\d{2,}[-*]?\d*\b", " ", text)
    text = re.sub(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", " ", text)
    text = re.sub(r"[*#]+", " ", text)
    text = re.sub(r"[^a-z0-9\s&./]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


_STOP_WORDS = frozenset(
    {
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
        "ach",
        "wire",
        "transfer",
        "online",
        "mobile",
        "deposit",
        "withdrawal",
        "transaction",
        "purchase",
        "recurring",
    }
)


def extract_vendor(description: str) -> str | None:
    """Heuristic vendor/payee from a bank description (first stable tokens)."""
    cleaned = clean_description(description)
    if not cleaned:
        return None
    words = [w for w in cleaned.split() if len(w) >= 3 and not w.isdigit() and w not in _STOP_WORDS]
    if not words:
        return None
    if len(words) >= 2 and len(f"{words[0]} {words[1]}") <= 40:
        return f"{words[0]} {words[1]}"
    return words[0][:40]


def extract_learn_keyword(description: str) -> str | None:
    """Pick a stable token/phrase from a cleaned description for passive learning."""
    return extract_vendor(description)


def _code_family(code: str) -> str:
    if code in INCOME_CODES:
        return "income"
    if code.startswith("5") or code in {"5010", "5020"}:
        return "cogs"
    if code.startswith("6") or code == SUSPENSE_CODE:
        return "expense"
    if code.startswith("3"):
        return "equity"
    if code.startswith("2"):
        return "liability"
    if code.startswith("1"):
        return "asset"
    return "other"


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
        if INCOME_DEFAULT_CODE not in accounts:
            accounts[INCOME_DEFAULT_CODE] = INCOME_DEFAULT_NAME
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

    def upgrade_income_seed_rules(self, tenant_id: uuid.UUID) -> dict[str, int]:
        """
        Fix legacy seeds that mapped customer payments / deposits to Cash 1010.
        Safe to call repeatedly; only touches source=seed rules pointing at 1010
        with payment/deposit keywords.
        """
        client = get_supabase_client()
        accounts = self._load_accounts(tenant_id)
        result = (
            client.table("account_rules")
            .select("id,keywords,account_code,source")
            .eq("tenant_id", str(tenant_id))
            .eq("source", "seed")
            .eq("account_code", "1010")
            .eq("is_active", True)
            .execute()
        )
        patched = 0
        # Any keyword that belongs on an income seed (legacy Cash 1010 mis-maps).
        sales_markers = {
            "payment thank",
            "thank you",
            "online payment",
            "autopay",
            "payment received",
            "customer payment",
            "client payment",
            "invoice payment",
            "stripe",
            "square",
            "paypal",
            "zelle from",
            "venmo from",
            "sales",
            "revenue",
            "pos sale",
        }
        income_markers = sales_markers | {
            "deposit",
            "wire in",
            "wire credit",
            "ach credit",
            "incoming wire",
            "mobile deposit",
            "remote deposit",
            "interest income",
            "dividend",
            "interest earned",
            "service fee income",
            "consulting income",
            "professional fee",
            "retainer",
        }
        for row in result.data or []:
            kws = {str(k).lower() for k in (row.get("keywords") or [])}
            if not kws.intersection(income_markers):
                continue
            new_code = INCOME_DEFAULT_CODE
            if kws.intersection(sales_markers):
                new_code = SALES_REVENUE_CODE
            client.table("account_rules").update(
                {
                    "account_code": new_code,
                    "account_name": accounts.get(new_code, INCOME_DEFAULT_NAME),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", row["id"]).execute()
            patched += 1

        # Ensure new income seed rows exist (idempotent by keyword overlap check)
        existing = (
            client.table("account_rules")
            .select("keywords,account_code")
            .eq("tenant_id", str(tenant_id))
            .eq("is_active", True)
            .execute()
        )
        existing_kw: set[str] = set()
        for row in existing.data or []:
            for k in row.get("keywords") or []:
                existing_kw.add(str(k).lower())

        inserted = 0
        merged = 0
        for keywords, code, default_name in DEFAULT_SEED_RULES:
            if code not in INCOME_CODES:
                continue
            action = self._merge_or_insert_seed_rule(
                tenant_id, list(keywords), code, default_name, accounts, existing_kw
            )
            if action == "inserted":
                inserted += 1
            elif action == "merged":
                merged += 1

        self.invalidate(tenant_id)
        return {
            "patched_cash_to_income": patched,
            "inserted_income_rules": inserted,
            "merged_income_keywords": merged,
        }

    def _collect_existing_keywords(self, tenant_id: uuid.UUID) -> set[str]:
        client = get_supabase_client()
        existing = (
            client.table("account_rules")
            .select("keywords")
            .eq("tenant_id", str(tenant_id))
            .eq("is_active", True)
            .execute()
        )
        existing_kw: set[str] = set()
        for row in existing.data or []:
            for k in row.get("keywords") or []:
                existing_kw.add(str(k).lower())
        return existing_kw

    def _merge_or_insert_seed_rule(
        self,
        tenant_id: uuid.UUID,
        keywords: list[str],
        code: str,
        default_name: str,
        accounts: dict[str, str],
        existing_kw: set[str],
        *,
        seed_rows_by_code: dict[str, list[dict[str, Any]]] | None = None,
    ) -> str:
        """
        Ensure every keyword for this seed lands on the right account_code.

        Legacy bug: skip-if-any-keyword-exists left new tokens (sabor, spa, …)
        out forever when an older meals/distributions seed already existed.
        """
        wanted = [k.lower() for k in keywords if k]
        if not wanted:
            return "noop"
        client = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        rows_for_code: list[dict[str, Any]] = []
        if seed_rows_by_code is not None:
            rows_for_code = list(seed_rows_by_code.get(code) or [])
        else:
            found = (
                client.table("account_rules")
                .select("id,keywords,account_code")
                .eq("tenant_id", str(tenant_id))
                .eq("account_code", code)
                .eq("source", "seed")
                .eq("is_active", True)
                .execute()
            )
            rows_for_code = list(found.data or [])

        if rows_for_code:
            primary = rows_for_code[0]
            current = [str(k).lower() for k in (primary.get("keywords") or [])]
            current_set = set(current)
            missing = [k for k in wanted if k not in current_set]
            if not missing:
                existing_kw.update(wanted)
                return "noop"
            merged = current + missing
            client.table("account_rules").update(
                {
                    "keywords": merged,
                    "account_name": accounts.get(code, default_name),
                    "updated_at": now,
                }
            ).eq("id", primary["id"]).execute()
            existing_kw.update(wanted)
            return "merged"

        # Brand-new seed row for this account code
        client.table("account_rules").insert(
            {
                "tenant_id": str(tenant_id),
                "keywords": wanted,
                "account_code": code,
                "account_name": accounts.get(code, default_name),
                "source": "seed",
                "is_active": True,
            }
        ).execute()
        existing_kw.update(wanted)
        if seed_rows_by_code is not None:
            seed_rows_by_code.setdefault(code, []).append(
                {"id": "new", "keywords": wanted, "account_code": code}
            )
        return "inserted"

    def _insert_seed_rule_if_missing(
        self,
        tenant_id: uuid.UUID,
        keywords: list[str],
        code: str,
        default_name: str,
        accounts: dict[str, str],
        existing_kw: set[str],
    ) -> bool:
        """Backward-compatible wrapper: True when a row was inserted or merged."""
        action = self._merge_or_insert_seed_rule(
            tenant_id, keywords, code, default_name, accounts, existing_kw
        )
        return action in {"inserted", "merged"}

    def upgrade_expense_seed_rules(self, tenant_id: uuid.UUID) -> dict[str, int]:
        """
        Fix legacy seeds: fuel on COGS 5010 → Gas 6160; social ads on 6060 → 6065;
        split travel/meals on 6050; merge missing expense keywords into existing seeds.
        """
        client = get_supabase_client()
        accounts = self._load_accounts(tenant_id)
        patched_fuel = 0
        patched_social = 0
        patched_travel_meals = 0

        seed_rows = (
            client.table("account_rules")
            .select("id,keywords,account_code,source")
            .eq("tenant_id", str(tenant_id))
            .eq("source", "seed")
            .eq("is_active", True)
            .execute()
        )
        for row in seed_rows.data or []:
            raw_kws = [str(k).lower() for k in (row.get("keywords") or [])]
            kws_set = set(raw_kws)
            rule_id = row["id"]
            code = str(row.get("account_code") or "")

            if code == "5010" and kws_set.intersection(FUEL_COGS_MARKERS):
                remaining = [k for k in raw_kws if k not in FUEL_COGS_MARKERS]
                fuel_kws = [k for k in raw_kws if k in FUEL_COGS_MARKERS]
                if remaining:
                    client.table("account_rules").update(
                        {
                            "keywords": remaining,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", rule_id).execute()
                else:
                    client.table("account_rules").update(
                        {
                            "account_code": "6160",
                            "account_name": accounts.get("6160", "Gas & Oil"),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", rule_id).execute()
                    patched_fuel += 1
                    continue
                existing_kw = self._collect_existing_keywords(tenant_id)
                if fuel_kws:
                    self._merge_or_insert_seed_rule(
                        tenant_id,
                        fuel_kws,
                        "6160",
                        "Gas & Oil",
                        accounts,
                        existing_kw,
                    )
                patched_fuel += 1
                continue

            if code == "6060" and kws_set.intersection(SOCIAL_ADS_MARKERS):
                remaining = [k for k in raw_kws if k not in SOCIAL_ADS_MARKERS]
                social_kws = [k for k in raw_kws if k in SOCIAL_ADS_MARKERS]
                if remaining:
                    client.table("account_rules").update(
                        {
                            "keywords": remaining,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", rule_id).execute()
                else:
                    client.table("account_rules").update(
                        {
                            "account_code": "6065",
                            "account_name": accounts.get("6065", "Social Media Ads"),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", rule_id).execute()
                    patched_social += 1
                    continue
                existing_kw = self._collect_existing_keywords(tenant_id)
                if social_kws:
                    self._merge_or_insert_seed_rule(
                        tenant_id,
                        social_kws,
                        "6065",
                        "Social Media Ads",
                        accounts,
                        existing_kw,
                    )
                patched_social += 1
                continue

            if code == "6050" and kws_set.intersection(TRAVEL_MARKERS) and not kws_set.intersection(MEALS_MARKERS):
                client.table("account_rules").update(
                    {
                        "account_code": "6055",
                        "account_name": accounts.get("6055", "Travel"),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("id", rule_id).execute()
                patched_travel_meals += 1
                continue

            # Drop ambiguous short token "bar" (matches "barnes", etc.)
            if code == "6050" and "bar" in kws_set:
                cleaned_kws = [k for k in raw_kws if k != "bar"]
                if cleaned_kws != raw_kws:
                    client.table("account_rules").update(
                        {
                            "keywords": cleaned_kws,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", rule_id).execute()
                    raw_kws = cleaned_kws
                    kws_set = set(raw_kws)

        # Refresh seed index after patches, then merge/insert full DEFAULT expense seeds
        seed_rows = (
            client.table("account_rules")
            .select("id,keywords,account_code")
            .eq("tenant_id", str(tenant_id))
            .eq("source", "seed")
            .eq("is_active", True)
            .execute()
        )
        by_code: dict[str, list[dict[str, Any]]] = {}
        for row in seed_rows.data or []:
            by_code.setdefault(str(row.get("account_code") or ""), []).append(row)

        existing_kw = self._collect_existing_keywords(tenant_id)
        inserted = 0
        merged = 0
        for keywords, code, default_name in DEFAULT_SEED_RULES:
            if code in INCOME_CODES:
                continue
            action = self._merge_or_insert_seed_rule(
                tenant_id,
                list(keywords),
                code,
                default_name,
                accounts,
                existing_kw,
                seed_rows_by_code=by_code,
            )
            if action == "inserted":
                inserted += 1
            elif action == "merged":
                merged += 1

        self.invalidate(tenant_id)
        return {
            "patched_fuel_cogs_to_gas": patched_fuel,
            "patched_social_to_6065": patched_social,
            "patched_travel_on_6050": patched_travel_meals,
            "inserted_expense_rules": inserted,
            "merged_expense_keywords": merged,
        }

    def classify(
        self,
        tenant_id: uuid.UUID,
        description: str,
        *,
        direction: Direction | None = None,
    ) -> CoAMatch:
        cleaned = clean_description(description)
        vendor = extract_vendor(description)
        accounts = self._load_accounts(tenant_id)
        rules = self._load_rules(tenant_id)

        effective_direction = direction
        if direction == "income" and looks_like_expense_merchant(cleaned):
            effective_direction = "expense"

        best: CoAMatch | None = None
        for rule in rules:
            keywords = rule.get("keywords") or []
            if isinstance(keywords, str):
                keywords = [keywords]
            hits = [kw for kw in keywords if kw and str(kw).lower() in cleaned]
            # Also try vendor phrase against each keyword (provider lookup)
            if not hits and vendor:
                hits = [kw for kw in keywords if kw and str(kw).lower() in vendor]
            if not hits:
                continue
            best_kw = max(hits, key=len)
            conf = min(0.55 + 0.08 * len(hits) + 0.02 * len(best_kw), 0.97)
            if rule.get("source") == "learned":
                conf = min(conf + 0.03, 0.98)
            # Vendor exact-ish boost
            if vendor and best_kw and best_kw in vendor:
                conf = min(conf + 0.04, 0.99)

            code = str(rule["account_code"])
            family = _code_family(code)

            # Direction filter: income credits must not land on Cash / OpEx
            if effective_direction == "income":
                if code in BLOCK_FOR_INCOME or family in {"expense", "cogs"}:
                    continue
                if family == "income":
                    conf = min(conf + 0.05, 0.99)
            elif effective_direction == "expense":
                if family == "income":
                    continue

            name = accounts.get(code) or str(rule.get("account_name") or code)
            candidate = CoAMatch(
                code=code,
                name=name,
                confidence=conf,
                matched_keyword=best_kw,
                source=str(rule.get("source") or "seed"),
                vendor=vendor,
            )
            if best is None or candidate.confidence > best.confidence:
                best = candidate
            elif (
                best is not None
                and abs(candidate.confidence - best.confidence) < 0.02
                and (candidate.matched_keyword or "")
                and len(candidate.matched_keyword or "") > len(best.matched_keyword or "")
            ):
                # Prefer longer keyword (e.g. "google ads" over "google" on Marketing)
                best = candidate

        if best:
            return best

        if effective_direction == "income":
            return CoAMatch(
                code=INCOME_DEFAULT_CODE,
                name=accounts.get(INCOME_DEFAULT_CODE, INCOME_DEFAULT_NAME),
                confidence=0.35,
                matched_keyword=vendor,
                source="income_default",
                vendor=vendor,
            )

        return CoAMatch(
            code=SUSPENSE_CODE,
            name=accounts.get(SUSPENSE_CODE, SUSPENSE_NAME),
            confidence=0.2,
            matched_keyword=None,
            source="suspense",
            vendor=vendor,
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
