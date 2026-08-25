"""
Rule-based Chart of Accounts classifier — $0, no OpenAI embeddings.

Matches transaction descriptions to CoA accounts using keywords / aliases.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from src.infrastructure.repositories.supabase_client import get_supabase_client

# Keywords → preferred account code (LedgerAI default CoA)
_KEYWORD_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("rent", "lease", "landlord"), "6020", "Rent Expense"),
    (("electric", "utility", "utilities", "water", "gas bill", "fpl"), "6030", "Utilities"),
    (("office depot", "staples", "supplies", "paper"), "6040", "Office Supplies"),
    (("uber", "lyft", "airline", "hotel", "marriott", "airbnb", "meal", "restaurant", "dunkin", "starbucks", "doordash", "grubhub"), "6050", "Travel & Meals"),
    (("ads", "advertis", "facebook ads", "google ads", "marketing", "highlevel"), "6060", "Marketing & Advertising"),
    (("legal", "attorney", "accountant", "cpa", "consult", "professional"), "6070", "Professional Services"),
    (("insurance", "geico", "state farm"), "6080", "Insurance"),
    (("repair", "maintenance", "hvac"), "6090", "Repairs & Maintenance"),
    (("software", "saas", "aws", "google cloud", "microsoft", "adobe", "github", "openai", "best buy", "apple.com", "technology"), "6100", "Technology & Software"),
    (("fee", "bank fee", "service charge", "overdraft", "interest charge"), "6110", "Bank Fees & Charges"),
    (("tax", "irs", "license", "permit"), "6130", "Taxes & Licenses"),
    (("salary", "payroll", "wage", "gusto", "adp"), "6010", "Salaries & Wages"),
    (("interest income", "dividend"), "4030", "Interest Income"),
    (("payment thank", "autopay", "payment - thank", "payment received", "online payment", "thank you"), "1010", "Cash and Cash Equivalents"),
    (("deposit", "wire in", "ach credit"), "1010", "Cash and Cash Equivalents"),
    (("costco", "walmart", "target", "amazon", "inventory", "exxon", "shell", "chevron", "gas #", "fuel"), "5010", "Cost of Goods Sold"),
]


@dataclass
class CoAMatch:
    code: str
    name: str
    confidence: float


class RuleCoAClassifier:
    """Classify descriptions against tenant CoA without paid embeddings."""

    def __init__(self) -> None:
        self._cache: dict[str, list[tuple[str, str]]] = {}

    def _load_accounts(self, tenant_id: uuid.UUID) -> list[tuple[str, str]]:
        key = str(tenant_id)
        if key in self._cache:
            return self._cache[key]
        client = get_supabase_client()
        result = (
            client.table("chart_of_accounts")
            .select("code,name")
            .eq("tenant_id", key)
            .execute()
        )
        rows = [(str(r["code"]), str(r["name"])) for r in (result.data or [])]
        if not rows:
            rows = list({(code, name) for _, code, name in _KEYWORD_RULES})
            rows.append(("6150", "Miscellaneous Expense"))
            rows.append(("9999", "Uncategorized"))
        self._cache[key] = rows
        return rows

    def classify(self, tenant_id: uuid.UUID, description: str) -> CoAMatch:
        text = (description or "").lower()
        text_norm = re.sub(r"[^a-z0-9\s&]", " ", text)
        accounts = {code: name for code, name in self._load_accounts(tenant_id)}

        best: CoAMatch | None = None
        for keywords, code, default_name in _KEYWORD_RULES:
            hits = sum(1 for kw in keywords if kw in text_norm)
            if hits == 0:
                continue
            conf = min(0.55 + 0.12 * hits, 0.95)
            name = accounts.get(code, default_name)
            candidate = CoAMatch(code=code, name=name, confidence=conf)
            if best is None or candidate.confidence > best.confidence:
                best = candidate

        # Also match account name tokens present in description
        for code, name in accounts.items():
            tokens = [t for t in re.split(r"\W+", name.lower()) if len(t) > 3]
            if tokens and all(t in text_norm for t in tokens[:2]):
                conf = 0.7
                if best is None or conf > best.confidence:
                    best = CoAMatch(code=code, name=name, confidence=conf)

        if best:
            return best
        return CoAMatch(
            code="9999" if "9999" in accounts or True else "6150",
            name=accounts.get("9999") or accounts.get("6150") or "Uncategorized",
            confidence=0.35,
        )
