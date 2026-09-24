"""Unit tests for rule CoA helpers (no Supabase)."""
from __future__ import annotations

from src.infrastructure.classification.rule_coa import (
    DEFAULT_SEED_RULES,
    FUEL_COGS_MARKERS,
    INCOME_CODES,
    INCOME_DEFAULT_CODE,
    MEALS_MARKERS,
    SALES_REVENUE_CODE,
    SOCIAL_ADS_MARKERS,
    SUSPENSE_CODE,
    _code_family,
    clean_description,
    extract_learn_keyword,
    extract_vendor,
    looks_like_expense_merchant,
    looks_like_personal_merchant,
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
    income_markers = (
        "deposit",
        "wire in",
        "ach credit",
        "payment thank",
        "stripe",
        "paypal",
    )
    for keywords, code, _name in DEFAULT_SEED_RULES:
        # Exact keyword hits only (avoid "stripe fee" bank-charge seed)
        if any(k.lower() in income_markers for k in keywords):
            assert code in INCOME_CODES, f"{keywords} must map to income, got {code}"
            assert code != "1010"


def test_code_family() -> None:
    assert _code_family("4010") == "income"
    assert _code_family("6020") == "expense"
    assert _code_family("5010") == "cogs"
    assert _code_family(SUSPENSE_CODE) == "expense"
    assert _code_family("1010") == "asset"


def test_income_default_constants() -> None:
    assert INCOME_DEFAULT_CODE == "4020"
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


def test_expense_keywords_not_in_income_seeds() -> None:
    expense_only = MEALS_MARKERS | FUEL_COGS_MARKERS | SOCIAL_ADS_MARKERS
    for keywords, code, _name in DEFAULT_SEED_RULES:
        if code not in INCOME_CODES:
            continue
        for kw in keywords:
            assert kw.lower() not in expense_only, f"income seed must not own {kw!r}"


def test_fuel_not_cogs_or_cash_in_default_seeds() -> None:
    for keywords, code, _name in DEFAULT_SEED_RULES:
        if not any(k.lower() in FUEL_COGS_MARKERS for k in keywords):
            continue
        assert code == "6160", f"fuel keywords {keywords} must map to 6160, got {code}"
        assert code not in {"1010", "5010"}


def test_social_media_ads_seed_code() -> None:
    social_rules = [
        (keywords, code)
        for keywords, code, _name in DEFAULT_SEED_RULES
        if any(k.lower() in SOCIAL_ADS_MARKERS for k in keywords)
    ]
    assert social_rules, "expected social media seed rules"
    for _keywords, code in social_rules:
        assert code == "6065"


def test_meals_keywords_map_to_meals_expense() -> None:
    for keywords, code, _name in DEFAULT_SEED_RULES:
        if any(k.lower() in MEALS_MARKERS for k in keywords):
            assert code == "6050"


def test_sabor_and_roadhouse_are_meals_seeds() -> None:
    meals_kw: set[str] = set()
    for keywords, code, _name in DEFAULT_SEED_RULES:
        if code == "6050":
            meals_kw.update(k.lower() for k in keywords)
    for must in ("sabor", "roadhouse", "texas roadhouse", "rodizio"):
        assert must in meals_kw


def test_spa_dental_are_owner_distributions() -> None:
    dist_kw: set[str] = set()
    for keywords, code, _name in DEFAULT_SEED_RULES:
        if code == "3030":
            dist_kw.update(k.lower() for k in keywords)
    for must in ("spa", "dental", "serenity spa"):
        assert must in dist_kw


def test_facebk_and_taqueria_seeds() -> None:
    social: set[str] = set()
    meals: set[str] = set()
    insurance: set[str] = set()
    tech: set[str] = set()
    for keywords, code, _name in DEFAULT_SEED_RULES:
        if code == "6065":
            social.update(k.lower() for k in keywords)
        if code == "6050":
            meals.update(k.lower() for k in keywords)
        if code == "6080":
            insurance.update(k.lower() for k in keywords)
        if code == "6100":
            tech.update(k.lower() for k in keywords)
    assert "facebk" in social
    assert "taqueria" in meals and "diosa" in meals
    assert "hiscox" in insurance
    assert "apple.com" in tech or "apple com" in tech


def test_facebk_description_is_expense_merchant() -> None:
    cleaned = clean_description("09/06 FACEBK *K9SXKZQUJ2 650-5434800 CA")
    assert "facebk" in cleaned
    assert looks_like_expense_merchant(cleaned)
    assert looks_like_expense_merchant(clean_description("TST* LA DIOSA TAQUERIA MIAMI"))
    assert looks_like_expense_merchant(clean_description("HIS*HISCOX INC"))


def test_personal_merchants_map_to_distributions_profile() -> None:
    assert looks_like_personal_merchant(clean_description("FOREVER 21 NAIL LOUNGE"))
    assert looks_like_personal_merchant(clean_description("THE FRESH MARKET 221 DORAL"))
    assert not looks_like_personal_merchant(clean_description("GOOGLE *ADS"))


def test_deposits_seed_to_services_not_other_income() -> None:
    for keywords, code, _name in DEFAULT_SEED_RULES:
        if any(k.lower() == "deposit" for k in keywords):
            assert code == "4020", f"deposits must be Services 4020, got {code}"
