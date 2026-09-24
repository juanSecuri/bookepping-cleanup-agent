"""
Rule-based Chart of Accounts classifier — $0, no OpenAI embeddings.

Flow: clean description → match account_rules (DB) → else builtin seeds → Suspense 9999.
Income ONLY for real bank deposits / explicit sales keywords — never invent 4020 for
unknown merchants. Personal Drive folders (e.g. Truist 5611) → Owner's Distributions 3030.
CC "PAYMENT - THANK YOU" → liability transfer 2010 (not P&L).

Passive learning: when user assigns a real CoA, persist a keyword rule.
Direction-aware: credits/income prefer revenue accounts; debits/expenses prefer expense/COGS.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from src.infrastructure.classification.client_bank_profile import (
    allows_income_classification,
    is_cc_payment_or_transfer,
    is_deposit_description,
    is_owner_contribution,
    profile_for_account,
)
from src.infrastructure.repositories.supabase_client import get_supabase_client

SUSPENSE_CODE = "9999"
SUSPENSE_NAME = "Gastos No Categorizados (Suspense)"
# Legacy constant retained for tests / upgrade helpers — classify() no longer invents 4020
INCOME_DEFAULT_CODE = "4020"
INCOME_DEFAULT_NAME = "Coaching & Consulting Services"
SALES_REVENUE_CODE = "4010"
SERVICE_REVENUE_CODE = "4020"
OTHER_INCOME_CODE = "4040"
TRANSFER_CODE = "2010"
TRANSFER_NAME = "Accounts Payable"
OWNER_EQUITY_CODE = "3010"
OWNER_DISTRIBUTIONS_CODE = "3030"

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
    "taqueria",
    "diosa",
    "bbq",
    "grill",
    "churrasc",
    "tst*",
    "tst ",
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
    "facebook",
    "facebk",
    "meta ads",
    "instagram",
    "tiktok",
    "social media",
    "insurance",
    "hiscox",
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
    "apple.com",
    "apple com",
    "interest charge",
    "finance charge",
    "kit.com",
    "costco",
    "walmart",
    "target",
    "amazon",
    "liquidat",
    "toastmasters",
    "fogo",
    "tocas",
    "twitter",
    " x.com",
    "x.com/",
    "parson",
    "esquire",
    "nuceria",
    "ahpnl",
    "canva",
    "chevron",
    "florsheim",
    "men's designers",
    "mens designers",
    "saman",
    "florida profess",
    "floridaprofes",
    "fpa*",
    "fpa ",
    "southwes",
    "southwest",
    "nori tori",
    "hat trick",
    "ups store",
    "shisho",
    "perry",
    "steakhouse",
)

_PERSONAL_MERCHANT_HINTS: tuple[str, ...] = (
    "forever 21",
    "nail lounge",
    "nail ",
    "salon",
    "sephora",
    "ulta",
    "fresh market",
    "publix",
    "whole foods",
    "wholefds",
    "trader joe",
    "grocery",
    "milam",
    "burlington",
    "dollar tree",
    "dollartree",
    "atm cash",
    "cash withdrawal",
    "netflix",
    "spotify",
    "disney+",
    "disney plus",
    "hulu",
    "roblox",
    "steam games",
    "playstation",
    "xbox",
    "clothing",
    "boutique",
    "medeye",
    "pharmacy",
)


def looks_like_expense_merchant(cleaned: str) -> bool:
    """True when description looks like OpEx/COGS/personal vendor, not operating revenue."""
    if not cleaned:
        return False
    if any(hint in cleaned for hint in _EXPENSE_MERCHANT_HINTS):
        return True
    if looks_like_personal_merchant(cleaned):
        return True
    # Toast / Square POS food vendors often look like "tst*name"
    if cleaned.startswith("tst") or " tst " in f" {cleaned} ":
        return True
    return False


def looks_like_personal_merchant(cleaned: str) -> bool:
    """Non-business spend for a consulting/bookkeeping firm → Owner's Distributions."""
    if not cleaned:
        return False
    return any(hint in cleaned for hint in _PERSONAL_MERCHANT_HINTS)


# Bootstrap seeds when tenant has no account_rules yet
# Names aligned to TPC QuickBooks CoA (Meals Expense, Social Media Ads, Insurance, …)
DEFAULT_SEED_RULES: list[tuple[list[str], str, str]] = [
    (["rent", "lease", "landlord"], "6020", "Rent or Lease"),
    (["electric", "utility", "utilities", "water", "fpl", "internet", "comcast", "att", "at&t"], "6030", "Utilities"),
    (["office depot", "staples", "supplies", "barnes"], "6040", "Office Expenses"),
    (
        [
            "restaurant",
            "starbucks",
            "doordash",
            "grubhub",
            "uber eats",
            "texas roadhouse",
            "roadhouse",
            "sabor",
            "rodizio",
            "pizza",
            "cafe",
            "cafeteria",
            "meals",
            "food",
            "taqueria",
            "diosa",
            "bbq",
            "grill",
            "churrasc",
            "churrascaso",
            "apocalypse",
            "mcdonald",
            "chipotle",
            "panera",
            "subway",
            "wingstop",
            "pollo",
            "sushi",
            "diner",
            "bistro",
            "cantina",
            "dunkin",
            "donut",
            "coffee",
            "saltgrass",
            "granja",
            "narcobollo",
            "nahuen",
            "tocas",
            "medellin",
            "fogo",
            "nori tori",
            "perry",
            "steakhouse",
            "ihop",
            "qdoba",
            "shisho",
            "caterin",
            "catering",
        ],
        "6050",
        "Meals Expense",
    ),
    (
        [
            "uber",
            "lyft",
            "airline",
            "hotel",
            "marriott",
            "hilton",
            "airbnb",
            "airfare",
            "lodging",
            "fairfield",
            "doubletree",
            "economybookings",
            "clearme",
            "southwest",
            "southwes",
            "american air",
            "delta air",
            "jetblue",
            "united air",
        ],
        "6055",
        "Travel",
    ),
    (
        [
            "marketing",
            "highlevel",
            "advertis",
            "branding",
            "promotional",
            "kennected",
            "brightmind",
            "process to profit",
            "sendinblue",
            "brevo",
            "hat trick",
            "awesome team",
            "anchormark",
            "cody burch",
            "viraleco",
            "envato",
            "eventbrite",
            "eb an evening",
        ],
        "6060",
        "Advertising",
    ),
    (
        [
            "google ads",
            "google *ads",
            "google",
            "facebook ads",
            "facebook",
            "facebk",
            "fb ads",
            "meta ads",
            "instagram ads",
            "instagram",
            "tiktok ads",
            "tiktok",
            "social media",
            "linkedin",
            "twitter",
            "x.com",
        ],
        "6065",
        "Social Media Ads",
    ),
    (
        [
            "legal",
            "attorney",
            "accountant",
            "cpa",
            "consult",
            "chamber",
            "dues",
            "bni",
            "kendall bus",
            "nra membership",
            "networking",
        ],
        "6070",
        "Legal & Professional Fees",
    ),
    (["insurance", "hiscox", "geico", "state farm", "liability"], "6080", "Insurance"),
    (["repair", "maintenance", "hvac", "carwash", "car wash"], "6090", "Repair & Maintenance"),
    (
        [
            "software",
            "saas",
            "aws",
            "vercel",
            "github",
            "microsoft",
            "adobe",
            "openai",
            "technology",
            "apple.com",
            "apple com",
            "apple.com/bill",
            "kit.com",
            "subscription",
            "zoom.us",
            "zoom",
            "hostinger",
            "namecheap",
            "name-cheap",
            "pipdecks",
            "ai innovision",
            "canva",
            "invoiceninja",
            "yoast",
            "freepik",
            "appsumo",
        ],
        "6100",
        "Dues & Subscriptions",
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
            "stripe fee",
        ],
        "6110",
        "Bank Charges",
    ),
    (["loan interest"], "6140", "Interest Expense"),
    (
        ["ups store", "the ups store", "fedex", "usps", "postage", "shipping"],
        "6040",
        "Office Expenses",
    ),
    (
        ["pcliquidations", "pc liquidations", "best buy", "micro center"],
        "1510",
        "Equipment",
    ),
    (
        [
            "sba eidl",
            "eidl loan",
            "loan payment",
            "loan luiz",
            "loan luis",
        ],
        "2510",
        "Long-Term Debt",
    ),
    (
        [
            "credit card pmt",
            "credit card payment",
            "online credit card",
            "mobile to ****",
            "payment to ****",
        ],
        TRANSFER_CODE,
        TRANSFER_NAME,
    ),
    (
        [
            "ahpnl",
            "lideres quanticos",
            "empowerment inc",
        ],
        "6070",
        "Legal & Professional Fees",
    ),
    (
        [
            "exxon",
            "shell",
            "chevron",
            "fuel",
            "7-eleven",
            "7 eleven",
            "wawa",
            "bp",
            "gas station",
            "sunoco",
        ],
        "6160",
        "Gas & Oil",
    ),
    (["parking", "toll", "sunpass"], "6170", "Parking & Tolls"),
    (["tax", "irs", "license", "permit"], "6130", "Taxes & Licenses"),
    (["salary", "payroll", "wage", "gusto", "adp"], "6010", "Payroll Expenses"),
    (["interest income", "dividend", "interest earned"], "4030", "Interest Earned"),
    (
        [
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
        ],
        "4010",
        "Sales",
    ),
    (
        [
            "service fee income",
            "consulting income",
            "professional fee",
            "retainer",
            "coaching",
            "deposit",
            "check deposit",
            "atm check deposit",
            "wire in",
            "wire credit",
            "ach credit",
            "incoming wire",
            "mobile deposit",
            "remote deposit",
        ],
        "4020",
        "Coaching & Consulting Services",
    ),
    (
        ["owner contribution", "owners contribution", "capital contribution", "aporte socio"],
        OWNER_EQUITY_CODE,
        "Owner's Equity",
    ),
    (
        [
            "payment - thank you",
            "payments - thank you",
            "online payment thank",
            "automatic payment",
            "thank you",
            "branch payment",
            "account close out",
            "payment reversal",
            "balance transfer",
        ],
        TRANSFER_CODE,
        TRANSFER_NAME,
    ),
    (
        [
            "florsheim",
            "men's designers",
            "mens designers",
            "saman",
            "nuceria",
            "psic",
            "anagdiaz",
            "ana diaz",
            "peterson academy",
        ],
        OWNER_DISTRIBUTIONS_CODE,
        "Owner's Distributions",
    ),
    (
        [
            "florida profess",
            "floridaprofes",
            "toastmasters",
            "parson institute",
            "esquire",
            "ahpnl",
            "lideres quanticos",
            "empowerment",
        ],
        "6070",
        "Legal & Professional Fees",
    ),
    (
        ["division of corp", "dos division", "sunbiz", "nic*-dos", "nic* dos"],
        "6130",
        "Taxes & Licenses",
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
            "forever 21",
            "nail lounge",
            "nail",
            "salon",
            "sephora",
            "ulta",
            "fresh market",
            "publix",
            "whole foods",
            "wholefds",
            "trader joe",
            "grocery",
            "milam",
            "burlington",
            "dollar tree",
            "dollartree",
            "atm cash",
            "cash withdrawal",
            "netflix",
            "spotify",
            "disney",
            "hulu",
            "medeye",
            "wm supercenter",
        ],
        "3030",
        "Owner's Distributions",
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
        "facebk",
        "fb ads",
        "meta ads",
        "instagram ads",
        "instagram",
        "tiktok ads",
        "tiktok",
        "social media",
        "linkedin",
        "twitter",
        "x.com",
    }
)
TRAVEL_MARKERS = frozenset(
    {"uber", "lyft", "airline", "hotel", "marriott", "airbnb", "airfare", "lodging"}
)
MEALS_MARKERS = frozenset(
    {
        "restaurant",
        "starbucks",
        "doordash",
        "grubhub",
        "uber eats",
        "texas roadhouse",
        "roadhouse",
        "sabor",
        "rodizio",
        "pizza",
        "cafe",
        "cafeteria",
        "meals",
        "food",
        "taqueria",
        "diosa",
        "bbq",
        "grill",
        "churrasc",
        "churrascaso",
        "apocalypse",
    }
)


@dataclass
class CoAMatch:
    code: str
    name: str
    confidence: float
    matched_keyword: str | None = None
    source: str = "none"  # seed | learned | manual | builtin | suspense | transfer | personal_profile | deposit
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
            "check deposit",
            "atm check deposit",
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

        # Legacy deposits parked on Other Income 4040 → Services 4020
        deposit_markers = {
            "deposit",
            "wire in",
            "wire credit",
            "ach credit",
            "incoming wire",
            "mobile deposit",
            "remote deposit",
        }
        rows_4040 = (
            client.table("account_rules")
            .select("id,keywords,account_code,source")
            .eq("tenant_id", str(tenant_id))
            .eq("source", "seed")
            .eq("account_code", OTHER_INCOME_CODE)
            .eq("is_active", True)
            .execute()
        )
        patched_4040 = 0
        for row in rows_4040.data or []:
            kws = {str(k).lower() for k in (row.get("keywords") or [])}
            if not kws.intersection(deposit_markers):
                continue
            client.table("account_rules").update(
                {
                    "account_code": SERVICE_REVENUE_CODE,
                    "account_name": accounts.get(
                        SERVICE_REVENUE_CODE, INCOME_DEFAULT_NAME
                    ),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", row["id"]).execute()
            patched_4040 += 1

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
            "patched_4040_deposits_to_services": patched_4040,
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

            if code == "6050" and kws_set.intersection(TRAVEL_MARKERS):
                # Split legacy "Travel & Meals" blob: travel → 6055, meals stay 6050
                travel_kws = [k for k in raw_kws if k in TRAVEL_MARKERS]
                remaining = [k for k in raw_kws if k not in TRAVEL_MARKERS]
                if remaining:
                    client.table("account_rules").update(
                        {
                            "keywords": remaining,
                            "account_code": "6050",
                            "account_name": accounts.get("6050", "Meals Expense"),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", rule_id).execute()
                else:
                    client.table("account_rules").update(
                        {
                            "account_code": "6055",
                            "account_name": accounts.get("6055", "Travel"),
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("id", rule_id).execute()
                    patched_travel_meals += 1
                    continue
                existing_kw = self._collect_existing_keywords(tenant_id)
                if travel_kws:
                    self._merge_or_insert_seed_rule(
                        tenant_id,
                        travel_kws,
                        "6055",
                        "Travel",
                        accounts,
                        existing_kw,
                    )
                patched_travel_meals += 1
                continue

            # Drop ambiguous short token "bar" / bare "ads" (false positives)
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

            if code == "6060" and "ads" in kws_set:
                cleaned_kws = [k for k in raw_kws if k != "ads"]
                if cleaned_kws != raw_kws:
                    client.table("account_rules").update(
                        {
                            "keywords": cleaned_kws,
                            "account_name": accounts.get("6060", "Advertising"),
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
        bank_account_number: str | None = None,
        folder_group: str | None = None,
        drive_path: str | None = None,
    ) -> CoAMatch:
        cleaned = clean_description(description)
        vendor = extract_vendor(description)
        accounts = self._load_accounts(tenant_id)
        rules = self._load_rules(tenant_id)
        bank_profile = profile_for_account(
            bank_account_number=bank_account_number,
            folder_group=folder_group,
            drive_path=drive_path,
        )

        # Owner capital in → equity (before deposit/income heuristics)
        if is_owner_contribution(cleaned):
            return CoAMatch(
                code=OWNER_EQUITY_CODE,
                name=accounts.get(OWNER_EQUITY_CODE, "Owner's Equity"),
                confidence=0.9,
                matched_keyword="contribution",
                source="owner_contribution",
                vendor=vendor,
            )

        # CC bill payments / transfers — balance sheet, never P&L sales/expense
        if is_cc_payment_or_transfer(cleaned):
            return CoAMatch(
                code=TRANSFER_CODE,
                name=accounts.get(TRANSFER_CODE, TRANSFER_NAME),
                confidence=0.88,
                matched_keyword="thank you",
                source="transfer",
                vendor=vendor,
            )

        # Personal card folder (e.g. Truist 5611): non-deposit spend → distributions
        if bank_profile == "personal" and not is_deposit_description(cleaned):
            return CoAMatch(
                code=OWNER_DISTRIBUTIONS_CODE,
                name=accounts.get(OWNER_DISTRIBUTIONS_CODE, "Owner's Distributions"),
                confidence=0.86,
                matched_keyword=vendor,
                source="personal_profile",
                vendor=vendor,
            )

        # If any expense/COGS/distributions keyword hits the description, force expense
        # (bank feeds often flip sign and mark Costco/restaurants as "income").
        expense_kw_hit = False
        for rule in rules:
            code = str(rule.get("account_code") or "")
            family = _code_family(code)
            if family not in {"expense", "cogs"} and code != OWNER_DISTRIBUTIONS_CODE:
                continue
            for kw in rule.get("keywords") or []:
                k = str(kw).lower()
                if k and (k in cleaned or (vendor and k in vendor)):
                    expense_kw_hit = True
                    break
            if expense_kw_hit:
                break

        is_expense_like = (
            expense_kw_hit
            or looks_like_expense_merchant(cleaned)
            or looks_like_personal_merchant(cleaned)
        )

        # Deposit-only / explicit-sales income: never invent Services for unknown merchants
        real_income = allows_income_classification(cleaned)
        effective_direction: Direction | None = direction
        if is_expense_like:
            effective_direction = "expense"
        elif real_income:
            effective_direction = "income"
        elif direction == "income" and not real_income:
            # Bank credit that is not a deposit/sales keyword → expense/suspense path
            effective_direction = "expense"

        best: CoAMatch | None = None
        for rule in rules:
            keywords = rule.get("keywords") or []
            if isinstance(keywords, str):
                keywords = [keywords]
            hits = [kw for kw in keywords if kw and str(kw).lower() in cleaned]
            if not hits and vendor:
                hits = [kw for kw in keywords if kw and str(kw).lower() in vendor]
            if not hits:
                continue
            best_kw = max(hits, key=len)
            conf = min(0.55 + 0.08 * len(hits) + 0.02 * len(best_kw), 0.97)
            if rule.get("source") == "learned":
                conf = min(conf + 0.03, 0.98)
            if vendor and best_kw and best_kw in vendor:
                conf = min(conf + 0.04, 0.99)

            code = str(rule["account_code"])
            family = _code_family(code)

            # Prefer Social Media Ads 6065 over generic Advertising 6060
            if code == "6060" and any(m in cleaned for m in SOCIAL_ADS_MARKERS):
                continue

            if effective_direction == "income":
                if code in BLOCK_FOR_INCOME or family in {"expense", "cogs", "equity"}:
                    continue
                if code == OTHER_INCOME_CODE:
                    conf = max(conf - 0.15, 0.4)
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
                best = candidate

        if best and best.code in INCOME_CODES and effective_direction == "expense":
            best = None
        if best and best.code in INCOME_CODES and (
            is_expense_like or not real_income
        ):
            # Never leave expense merchants / non-deposits on revenue codes
            best = None

        if best:
            # Fuel must stay Gas 6160 even if a stale COGS rule still matches
            if best.code == "5010" and any(m in cleaned for m in FUEL_COGS_MARKERS):
                return CoAMatch(
                    code="6160",
                    name=accounts.get("6160", "Gas & Oil"),
                    confidence=max(best.confidence, 0.85),
                    matched_keyword=best.matched_keyword,
                    source="fuel_override",
                    vendor=vendor,
                )
            return best

        if effective_direction != "income" and looks_like_personal_merchant(cleaned):
            return CoAMatch(
                code=OWNER_DISTRIBUTIONS_CODE,
                name=accounts.get(OWNER_DISTRIBUTIONS_CODE, "Owner's Distributions"),
                confidence=0.72,
                matched_keyword=vendor,
                source="personal_profile",
                vendor=vendor,
            )

        # Real deposit with no keyword hit → Services (operating revenue)
        if is_deposit_description(cleaned) and not is_expense_like:
            return CoAMatch(
                code=SERVICE_REVENUE_CODE,
                name=accounts.get(SERVICE_REVENUE_CODE, INCOME_DEFAULT_NAME),
                confidence=0.7,
                matched_keyword="deposit",
                source="deposit",
                vendor=vendor,
            )

        # Never invent income_default 4020 for unknown lines
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
