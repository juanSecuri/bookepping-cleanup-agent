"""MyXcell / TPC Drive-folder bank profile → business vs personal spend.

Source of truth = union of:
  (a) every distinct folder_group / drive_path / bank_account seen in synced documents
  (b) full Google Drive tree under My Xcell Network CORP (screenshot + unsynced folders)

Synced in DB today: Citi 1802, Elan 3647/5607, Truist 1203 & 4461, Wells Fargo 8398,
Citi Best Buy (folder only). Unsynced but must classify when they land: Truist Personal
5611, Jetstream 4493, Dade County FCU, Chase 5841/9679, more Wells ####.
"""
from __future__ import annotations

import re
from typing import Literal

BankProfile = Literal["personal", "business", "coa_reference"]

# Last-4 (or folder account id) → profile. Includes synced + Drive-tree accounts.
MYXCELL_BANK_PROFILE: dict[str, BankProfile] = {
    # --- Synced documents (live DB) ---
    "1802": "business",  # Citi Costco 1802
    "3647": "business",  # Elan 3647 (5607)
    "5607": "business",  # Elan alt number in folder name
    "1203": "business",  # Truist Credit Card 1203 (empresa)
    "4461": "business",  # Truist Checking 4461
    "8398": "business",  # Wells Fargo Credit Cards …/8398
    "4809": "business",  # Wells digit seen under WF tree
    "8431": "business",  # Wells digit seen under WF tree
    # --- Drive tree (screenshot) — may be unsynced yet ---
    "5611": "personal",  # Truist Personal Credit Card → Owner's Distributions
    "4493": "business",  # Jetstream 4493
    "5841": "business",  # Chase Credit Card 5841
    "9679": "business",  # Chase Checking 9679
}

# Human-readable Drive folder → profile (matched against folder_group / drive_path)
MYXCELL_FOLDER_PROFILES: list[tuple[str, BankProfile, str]] = [
    ("truist personal credit card 5611", "personal", "Truist Personal Credit Card 5611"),
    ("truist personal", "personal", "Truist Personal Credit Card 5611"),
    ("truist credit card 1203", "business", "Truist Credit Card 1203"),
    ("truist checking 4461", "business", "Truist Checking 4461"),
    ("wells fargo credit cards", "business", "Wells Fargo Credit Cards (various)"),
    ("wells fargo", "business", "Wells Fargo Credit Cards (various)"),
    ("jetstream 4493", "business", "Jetstream 4493"),
    ("jetstream", "business", "Jetstream 4493"),
    ("elan 3647", "business", "Elan 3647 (5607)"),
    ("elan", "business", "Elan 3647 (5607)"),
    ("dade county federal credit union", "business", "Dade County Federal Credit Union"),
    ("dade county", "business", "Dade County Federal Credit Union"),
    ("citi costco 1802", "business", "Citi Costco 1802"),
    ("citi costco", "business", "Citi Costco 1802"),
    ("citi best buy", "business", "Citi Best Buy"),
    ("best buy", "business", "Citi Best Buy"),
    ("chase credit card 5841", "business", "Chase Credit Card 5841"),
    ("chase checking 9679", "business", "Chase Checking 9679"),
    ("chase credit card", "business", "Chase Credit Card 5841"),
    ("chase checking", "business", "Chase Checking 9679"),
    ("bookkeeping info", "coa_reference", "Bookkeeping Info"),
]

PERSONAL_ACCOUNT_HINTS = (
    "personal",
    "owners",
    "owner's",
    "5611",
    "truist personal",
)

# Synced vs expected (for ops notes / bookkeeper pass diagnostics)
SYNCED_ACCOUNT_TAILS: frozenset[str] = frozenset(
    {"1802", "3647", "5607", "1203", "4461", "8398", "4809", "8431"}
)
UNSYNCED_DRIVE_FOLDERS: tuple[str, ...] = (
    "Truist Personal Credit Card 5611",
    "Jetstream 4493",
    "Dade County Federal Credit Union",
    "Chase Credit Card 5841",
    "Chase Checking 9679",
)

_ACCOUNT_TAIL_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def extract_account_tail(
    bank_account_number: str | None = None,
    folder_group: str | None = None,
    drive_path: str | None = None,
) -> str | None:
    """Best-effort last-4 from explicit account, folder_group, or drive_path."""
    acct = (bank_account_number or "").strip()
    if len(acct) >= 4 and acct[-4:].isdigit():
        return acct[-4:]
    hay = f"{folder_group or ''} {drive_path or ''}"
    # Prefer known profile keys appearing in path
    for known in MYXCELL_BANK_PROFILE:
        if known in hay:
            return known
    matches = _ACCOUNT_TAIL_RE.findall(hay)
    for m in matches:
        if m.startswith("20") and len(m) == 4:
            continue  # skip years 20xx
        return m
    return None


def profile_for_account(
    bank_account_number: str | None = None,
    folder_group: str | None = None,
    drive_path: str | None = None,
) -> BankProfile:
    """Return 'personal' | 'business' | 'coa_reference'."""
    hay = f"{folder_group or ''} {drive_path or ''}".lower()
    for needle, profile, _label in MYXCELL_FOLDER_PROFILES:
        if needle in hay:
            return profile

    tail = extract_account_tail(bank_account_number, folder_group, drive_path)
    if tail and tail in MYXCELL_BANK_PROFILE:
        return MYXCELL_BANK_PROFILE[tail]

    if any(h in hay for h in PERSONAL_ACCOUNT_HINTS):
        return "personal"
    return "business"


# Explicit last-4 → Drive folder label (synced + screenshot)
ACCOUNT_FOLDER_LABELS: dict[str, str] = {
    "5611": "Truist Personal Credit Card 5611",
    "1203": "Truist Credit Card 1203",
    "4461": "Truist Checking 4461",
    "1802": "Citi Costco 1802",
    "3647": "Elan 3647 (5607)",
    "5607": "Elan 3647 (5607)",
    "8398": "Wells Fargo Credit Cards (various) / 8398",
    "4809": "Wells Fargo Credit Cards (various) / 4809",
    "8431": "Wells Fargo Credit Cards (various) / 8431",
    "4493": "Jetstream 4493",
    "5841": "Chase Credit Card 5841",
    "9679": "Chase Checking 9679",
}


def folder_label_for(
    bank_account_number: str | None = None,
    folder_group: str | None = None,
    drive_path: str | None = None,
) -> str:
    """Human folder name for diagnostics."""
    hay = f"{folder_group or ''} {drive_path or ''}".lower()
    for needle, _profile, label in MYXCELL_FOLDER_PROFILES:
        if needle in hay:
            return label
    tail = extract_account_tail(bank_account_number, folder_group, drive_path)
    if tail and tail in ACCOUNT_FOLDER_LABELS:
        return ACCOUNT_FOLDER_LABELS[tail]
    if folder_group:
        return folder_group
    if tail:
        return f"Account …{tail}"
    return "Unknown"


def all_drive_folder_profiles() -> list[dict[str, str]]:
    """Full account→profile table (synced + Drive screenshot)."""
    rows: list[dict[str, str]] = []
    seen_folders: set[str] = set()
    for acct, profile in sorted(MYXCELL_BANK_PROFILE.items()):
        label = ACCOUNT_FOLDER_LABELS.get(acct, f"Account …{acct}")
        sync = "synced" if acct in SYNCED_ACCOUNT_TAILS else "unsynced_drive"
        rows.append(
            {
                "account": acct,
                "folder": label,
                "profile": profile,
                "sync_status": sync,
            }
        )
        seen_folders.add(label)
    # Folders without a dedicated #### row yet
    extra = (
        ("—", "Dade County Federal Credit Union", "business", "unsynced_drive"),
        ("—", "Citi Best Buy", "business", "synced_folder_no_acct"),
        ("—", "Bookkeeping Info", "coa_reference", "coa_reference"),
    )
    for acct, label, profile, sync in extra:
        if label in seen_folders:
            continue
        rows.append(
            {
                "account": acct,
                "folder": label,
                "profile": profile,
                "sync_status": sync,
            }
        )
        seen_folders.add(label)
    return rows


def is_cc_payment_or_transfer(cleaned: str) -> bool:
    """Credit-card bill payments / account transfers — not P&L income or expense."""
    if not cleaned:
        return False
    markers = (
        "thank you",
        "payment - thank",
        "payments - thank",
        "online payment thank",
        "automatic payment",
        "autopay",
        "payment thank",
        "branch payment",
        "account close out",
        "payment reversal",
        "balance transfer",
    )
    return any(m in cleaned for m in markers)


def is_owner_contribution(cleaned: str) -> bool:
    if not cleaned:
        return False
    markers = (
        "owner contribution",
        "owners contribution",
        "owner's contribution",
        "capital contribution",
        "aporte socio",
        "aporte de capital",
        "owner equity",
    )
    return any(m in cleaned for m in markers)


def is_deposit_description(cleaned: str) -> bool:
    """Income only when the line is clearly a deposit / wire-in (not CC 'thank you')."""
    if not cleaned:
        return False
    if is_cc_payment_or_transfer(cleaned):
        return False
    if is_owner_contribution(cleaned):
        return False
    markers = (
        "deposit",
        "dep ",
        " dep",
        "check deposit",
        "atm check deposit",
        "mobile deposit",
        "remote deposit",
        "wire in",
        "wire credit",
        "incoming wire",
        "ach credit",
    )
    # Bare "dep" token
    tokens = cleaned.split()
    if "dep" in tokens:
        return True
    return any(m in cleaned for m in markers)


def is_explicit_sales_income(cleaned: str) -> bool:
    """Real operating receipts (processor / customer payment) — not unknown merchants."""
    if not cleaned or is_cc_payment_or_transfer(cleaned):
        return False
    markers = (
        "payment received",
        "customer payment",
        "client payment",
        "invoice payment",
        "stripe",
        "square",
        "paypal",
        "zelle from",
        "venmo from",
        "pos sale",
        "consulting income",
        "service fee income",
        "professional fee income",
        "retainer",
        "coaching income",
    )
    return any(m in cleaned for m in markers)


def allows_income_classification(cleaned: str) -> bool:
    """True only for deposits or explicit sales keywords — never unknown merchants."""
    return is_deposit_description(cleaned) or is_explicit_sales_income(cleaned)
