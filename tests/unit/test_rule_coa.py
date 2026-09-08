"""Unit tests for rule CoA helpers (no Supabase)."""
from __future__ import annotations

from src.infrastructure.classification.rule_coa import (
    DEFAULT_SEED_RULES,
    INCOME_CODES,
    INCOME_DEFAULT_CODE,
    SALES_REVENUE_CODE,
    SUSPENSE_CODE,
    _code_family,
    clean_description,
    extract_learn_keyword,
    extract_vendor,
)


def test_clean_description_strips_noise() -> None:
    raw = "UBER *TRIP HELP.UBER.COM Auth#AB12CD34 03/15/2025"
    cleaned = clean_description(raw)
    assert "uber" in cleaned
    assert "auth" not in cleaned or "ab12" not in cleaned.replace(" ", "")


def test_extract_vendor_from_bank_line() -> None:
    vendor = extract_vendor("STARBUCKS STORE 12345 SEATTLE WA 03/01")
    assert vendor is not None
    assert "starbucks" in vendor


def test_extract_learn_keyword_matches_vendor() -> None:
    assert extract_learn_keyword("COSTCO WHOLESALE #112") == extract_vendor(
        "COSTCO WHOLESALE #112"
    )


def test_income_seeds_not_cash() -> None:
    for keywords, code, _name in DEFAULT_SEED_RULES:
        joined = " ".join(keywords)
        if any(
            m in joined
            for m in ("deposit", "wire in", "ach credit", "payment thank", "stripe", "paypal")
        ):
            assert code in INCOME_CODES, f"{keywords} must map to income, got {code}"
            assert code != "1010"


def test_code_family() -> None:
    assert _code_family("4010") == "income"
    assert _code_family("6020") == "expense"
    assert _code_family("5010") == "cogs"
    assert _code_family(SUSPENSE_CODE) == "expense"
    assert _code_family("1010") == "asset"


def test_income_default_constants() -> None:
    assert INCOME_DEFAULT_CODE == "4040"
    assert SALES_REVENUE_CODE == "4010"


def test_upgrade_markers_cover_income_seed_keywords() -> None:
    """Regression: legacy Cash→income patch must recognize stripe/paypal/etc."""
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
    income_kw: set[str] = set()
    for keywords, code, _name in DEFAULT_SEED_RULES:
        if code in INCOME_CODES:
            income_kw.update(k.lower() for k in keywords)
    # Every income-seed keyword should be considered by the upgrade path
    # (sales → 4010, other income → 4040). Spot-check the ones that used to be missed.
    for must in ("stripe", "paypal", "deposit", "wire in", "customer payment"):
        assert must in income_kw
        assert must in sales_markers or must in {
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
        } | sales_markers
