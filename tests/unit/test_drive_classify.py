"""Drive path classification for nested bank / account / year folders."""
from src.infrastructure.drive.classify import classify_drive_file


def test_wells_nested_account_year() -> None:
    plan = classify_drive_file(
        "May 2025.pdf",
        "TPC Clients/My Xcell Network CORP/Wells Fargo Credit Cards (various)/8398/2025",
        "application/pdf",
    )
    assert plan.kind == "statement"
    assert plan.bank_name == "Wells Fargo"
    assert plan.bank_account_number == "8398"
    assert plan.fiscal_year == "2025"
    assert plan.statement_month == "2025-05"
    assert plan.folder_group == "Wells Fargo / 8398 / 2025"


def test_truist_account_in_folder_name() -> None:
    plan = classify_drive_file(
        "062226.pdf",
        "TPC Clients/My Xcell Network CORP/Truist Checking 4461/2026",
        "application/pdf",
    )
    assert plan.kind == "statement"
    assert plan.bank_name == "Truist"
    assert plan.bank_account_number == "4461"
    assert plan.fiscal_year == "2026"
    assert "Truist" in (plan.folder_group or "")
    assert "4461" in (plan.folder_group or "")


def test_chase_credit_card() -> None:
    plan = classify_drive_file(
        "statement.pdf",
        "My Xcell Network CORP/Chase Credit Card 5841/2024",
        "application/pdf",
    )
    assert plan.bank_name == "Chase"
    assert plan.bank_account_number == "5841"
    assert plan.fiscal_year == "2024"
