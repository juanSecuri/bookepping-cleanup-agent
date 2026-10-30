"""
Statement ("funding") accounts for the Balance Sheet.

Every verified transaction was read from one statement: a bank account or a credit card.
That statement account is the *other side* of the posting:

    bank  → asset      (Bank Accounts):   money in  +, money out −
    card  → liability  (Credit Cards):    charges   +, payments  −

The account comes from the Drive folder of the source document, e.g.
``Truist Checking 4461/2025/…`` or
``My Xcell Network CORP/Wells Fargo Credit Cards (various)/8398/2025/…``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

BANK_ACCOUNTS = "Bank Accounts"
CREDIT_CARDS = "Credit Cards"

_CARD_WORDS = (
    "credit card",
    "card",
    "elan",
    "citi",
    "costco",
    "best buy",
    "amex",
    "american express",
    "visa",
    "mastercard",
    "discover",
    "capital one",
)
_BANK_WORDS = ("checking", "savings", "money market", "business account", "bank account")
_PAYMENT_MEMO = re.compile(r"payment[s]?\s*[-,]?\s*thank you|autopay|automatic payment", re.I)
_YEAR = re.compile(r"^(19|20)\d{2}$")


@dataclass(frozen=True)
class FundingAccount:
    key: str  # stable code used as the Balance Sheet line code
    name: str
    kind: str  # "bank" | "card"

    @property
    def subcategory(self) -> str:
        return CREDIT_CARDS if self.kind == "card" else BANK_ACCOUNTS


def account_kind(*texts: str) -> str | None:
    blob = " ".join(t.lower() for t in texts if t)
    if any(w in blob for w in _BANK_WORDS):
        return "bank"
    if any(w in blob for w in _CARD_WORDS):
        return "card"
    return None


def _folder_label(drive_path: str, bank: str, number: str) -> str:
    """The folder that names the account (skip the company root and year folders)."""
    parts = [p.strip() for p in PurePosixPath(drive_path).parts[:-1] if p.strip()]
    parts = [p for p in parts if not _YEAR.match(p)]
    for part in parts:
        low = part.lower()
        if (bank and bank.lower().split()[0] in low) or (number and number in part):
            return part
    return parts[0] if parts else ""


def _clean_folder(name: str) -> str:
    name = re.sub(r"\s*\((various|varios|several)\)", "", name, flags=re.I)
    return re.sub(r"credit cards\b", "Credit Card", name, flags=re.I).strip()


def funding_from_document(doc: dict) -> FundingAccount | None:
    payload = doc.get("queue_payload") or {}
    bank = str(payload.get("bank_name") or doc.get("vendor") or "").strip()
    number = str(payload.get("bank_account_number") or "").strip()
    if set(number) <= {"0"}:  # "0000" = account number not read from the statement
        number = ""
    drive_path = str(doc.get("drive_path") or "")
    folder = _clean_folder(_folder_label(drive_path, bank, number))
    if not (bank or folder):
        return None
    kind = account_kind(drive_path, folder) or account_kind(bank) or "bank"
    name = folder or " ".join(x for x in (bank, "Credit Card" if kind == "card" else "") if x)
    if number and number not in name:
        name = f"{name} {number}"
    first = bank.lower().split()[0] if bank else ""
    if first and first not in name.lower():
        name = f"{bank} {name}"
    key = f"{kind}:{first or folder.lower()}:{number or folder.lower()}"
    return FundingAccount(key=key, name=name, kind=kind)


def file_stem(transaction) -> str:
    meta = getattr(transaction, "metadata", None)
    raw = str(getattr(meta, "raw_file_path", "") or "")
    return PurePosixPath(raw).stem if raw else ""


def build_funding_resolver(
    documents: Iterable[dict], transactions: Iterable
) -> Callable[[object], FundingAccount | None]:
    """Map each transaction to its statement account (bank or card)."""
    by_doc: dict[str, FundingAccount] = {}
    for doc in documents:
        fa = funding_from_document(doc)
        if fa and doc.get("id"):
            by_doc[str(doc["id"])] = fa

    # Statements whose document was removed: a file with card-payment memos is a card.
    orphan_cards: set[str] = set()
    for t in transactions:
        stem = file_stem(t)
        if stem and stem not in by_doc and _PAYMENT_MEMO.search(str(t.description or "")):
            orphan_cards.add(stem)

    def resolve(t) -> FundingAccount | None:
        stem = file_stem(t)
        if stem in by_doc:
            return by_doc[stem]
        if stem in orphan_cards:
            return FundingAccount(
                key=f"card:upload:{stem}", name="Credit Card (CSV import)", kind="card"
            )
        return None

    return resolve


def is_card_payment_memo(description: str | None) -> bool:
    return bool(_PAYMENT_MEMO.search(description or ""))
