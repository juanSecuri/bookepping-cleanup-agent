"""Unit tests for MyXcell Drive-folder bank profiles (no Supabase)."""
from __future__ import annotations

from src.infrastructure.classification.client_bank_profile import (
    MYXCELL_BANK_PROFILE,
    UNSYNCED_DRIVE_FOLDERS,
    all_drive_folder_profiles,
    allows_income_classification,
    is_cc_payment_or_transfer,
    is_deposit_description,
    is_owner_contribution,
    profile_for_account,
)


def test_personal_card_5611() -> None:
    assert profile_for_account(bank_account_number="5611") == "personal"
    assert (
        profile_for_account(folder_group="Truist Personal Credit Card 5611 / 2025")
        == "personal"
    )


def test_business_cards_from_synced_and_drive() -> None:
    for acct in ("1203", "4461", "1802", "3647", "5607", "8398", "4493", "5841", "9679"):
        assert profile_for_account(bank_account_number=acct) == "business", acct


def test_folder_path_elan_and_wells() -> None:
    assert (
        profile_for_account(drive_path="My Xcell Network CORP/Elan 3647 (5607)/2025")
        == "business"
    )
    assert (
        profile_for_account(
            drive_path="My Xcell Network CORP/Wells Fargo Credit Cards (various)/8398/2025"
        )
        == "business"
    )


def test_deposit_only_income() -> None:
    assert is_deposit_description("truist atm check deposit doral")
    assert is_deposit_description("mobile deposit")
    assert is_deposit_description("wire in from client")
    assert allows_income_classification("stripe payout")
    assert not is_deposit_description("payment - thank you")
    assert not is_deposit_description("canva subscription")
    assert not allows_income_classification("canva i04441")
    assert not allows_income_classification("florsheim shoe miami")


def test_cc_thank_you_is_transfer_not_income() -> None:
    assert is_cc_payment_or_transfer("payment - thank you")
    assert is_cc_payment_or_transfer("online payment thank you")
    assert is_cc_payment_or_transfer("automatic payment - thank you")
    assert not allows_income_classification("payment - thank you")


def test_owner_contribution() -> None:
    assert is_owner_contribution("owner contribution 5000")
    assert is_owner_contribution("capital contribution")
    assert not is_deposit_description("owner contribution")


def test_full_profile_table_covers_drive_tree() -> None:
    rows = all_drive_folder_profiles()
    accounts = {r["account"] for r in rows}
    for must in MYXCELL_BANK_PROFILE:
        assert must in accounts
    folders = {r["folder"].lower() for r in rows}
    assert any("5611" in f or "personal" in f for f in folders)
    assert any("jetstream" in f for f in folders)
    assert any("chase" in f for f in folders)
    assert any("dade" in f for f in folders)
    assert UNSYNCED_DRIVE_FOLDERS
