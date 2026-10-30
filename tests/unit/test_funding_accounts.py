"""Statement accounts (bank / card) → Balance Sheet double entry (My Xcell folder layout)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.domain.models.enums import DocumentSource, TransactionStatus, TransactionType
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.reports.funding_accounts import (
    build_funding_resolver,
    funding_from_document,
)
from src.use_cases.emit_period_reports import CLEARING_CODE, EmitPeriodReportsUseCase

INC, EXP = TransactionType.INCOME, TransactionType.EXPENSE


def _doc(doc_id: str, path: str, bank: str, number: str) -> dict:
    return {
        "id": doc_id,
        "drive_path": path,
        "queue_payload": {"bank_name": bank, "bank_account_number": number},
    }


DOCS = [
    _doc("chk", "Truist Checking 4461/11/01/stmt.pdf", "Truist", "4461"),
    _doc("tcc", "Truist Credit Card 1203/2025/May, 2025.pdf", "Truist", "1203"),
    _doc("elan", "Elan 3647 (5607)/2025/stmt.pdf", "Elan", "3647"),
    _doc("bb", "Citi Best Buy/2025/stmt.pdf", "Citi", "0000"),
    _doc(
        "wf",
        "My Xcell Network CORP/Wells Fargo Credit Cards (various)/8398/2025/x.pdf",
        "Wells Fargo",
        "8398",
    ),
]


@pytest.mark.parametrize(
    ("doc", "name", "kind"),
    [
        (DOCS[0], "Truist Checking 4461", "bank"),
        (DOCS[1], "Truist Credit Card 1203", "card"),
        (DOCS[2], "Elan 3647 (5607)", "card"),
        (DOCS[3], "Citi Best Buy", "card"),
        (DOCS[4], "Wells Fargo Credit Card 8398", "card"),
    ],
)
def test_account_name_and_kind_from_drive_folder(doc: dict, name: str, kind: str) -> None:
    fa = funding_from_document(doc)
    assert fa is not None
    assert (fa.name, fa.kind) == (name, kind)


def _tx(day: date, amount: str, tx_type, code: str, source: str, desc: str = "x"):
    return FinancialTransaction(
        tenant_id=uuid.uuid4(),
        transaction_date=day,
        description=desc,
        amount=Decimal(amount),
        currency="USD",
        transaction_type=tx_type,
        chart_of_accounts_code=code,
        chart_of_accounts_name=code,
        status=TransactionStatus.VERIFIED,
        metadata=ExtractionMetadata(
            source=DocumentSource.BANK_STATEMENT,
            raw_file_path=f"/var/data/ledgerai_uploads/{source}.pdf",
            extraction_model="test",
            confidence_score=1.0,
        ),
    )


def test_orphan_statement_with_card_payments_is_a_card() -> None:
    txs = [_tx(date(2025, 1, 1), "10", EXP, "2010", "lost-csv", "PAYMENT - THANK YOU")]
    resolve = build_funding_resolver(DOCS, txs)
    fa = resolve(txs[0])
    assert fa is not None and fa.kind == "card"


COA = {
    "1010": {"name": "Cash", "account_type": "asset", "subcategory": "Current Assets"},
    "2010": {
        "name": "Accounts Payable",
        "account_type": "liability",
        "subcategory": "Current Liabilities",
    },
    "2510": {
        "name": "Long-Term Debt",
        "account_type": "liability",
        "subcategory": "Long-Term Liabilities",
    },
    "3030": {"name": "Owner's Draws", "account_type": "equity", "subcategory": "Equity"},
    "4020": {
        "name": "Service Revenue",
        "account_type": "income",
        "subcategory": "Operating Revenue",
    },
    "6050": {
        "name": "Travel & Meals",
        "account_type": "expense",
        "subcategory": "Operating Expenses",
    },
}

ROWS = [
    _tx(date(2025, 2, 1), "1000", INC, "4020", "chk"),  # deposit → bank +1000
    _tx(date(2025, 2, 3), "300", EXP, "6050", "tcc"),  # card charge → card +300
    _tx(date(2025, 2, 5), "40", EXP, "3030", "elan"),  # personal on card → card +40
    _tx(date(2025, 2, 20), "300", EXP, "2010", "chk", "TRUIST ONLINE CREDIT CARD PMT"),
    _tx(date(2025, 2, 21), "300", INC, "2010", "tcc", "PAYMENTS - THANK YOU"),
    _tx(date(2025, 2, 24), "185", EXP, "2510", "chk", "SBA EIDL LOAN"),  # loan ↓
    # CSV import stored the card payment as a charge: still a credit on the card
    _tx(date(2025, 2, 25), "50", EXP, "2010", "elan", "PAYMENT - THANK YOU"),
]


async def _bundle():
    repo = AsyncMock()

    async def by_range(_wid, *, date_from=None, date_to=None, **_):
        return [
            r
            for r in ROWS
            if (not date_from or str(r.transaction_date) >= date_from)
            and (not date_to or str(r.transaction_date) <= date_to)
        ]

    repo.list_by_tenant_date_range = by_range
    uc = EmitPeriodReportsUseCase(transaction_repo=repo)
    uc._coa_accounts = lambda _tid: COA  # type: ignore[method-assign]
    uc._statement_documents = lambda _tid: DOCS  # type: ignore[method-assign]
    return await uc.execute(uuid.uuid4(), fiscal_year="2025")


@pytest.mark.asyncio
async def test_balance_sheet_posts_each_statement_account() -> None:
    bs = (await _bundle()).balance_sheet
    assets = {a["name"]: a for a in bs["assets"]}
    liabs = {x["name"]: x for x in bs["liabilities"]}
    equity = {x["name"]: x for x in bs["equity"]}

    # Bank: +1000 deposit − 300 card payment − 185 loan payment
    assert assets["Truist Checking 4461"]["amount"] == pytest.approx(515.0)
    assert assets["Truist Checking 4461"]["subcategory"] == "Bank Accounts"
    # Card: +300 charge − 300 payment received
    assert liabs["Truist Credit Card 1203"]["amount"] == pytest.approx(0.0)
    assert liabs["Truist Credit Card 1203"]["subcategory"] == "Credit Cards"
    # Elan: +40 owner charge − 50 payment (CSV sign corrected)
    assert liabs["Elan 3647 (5607)"]["amount"] == pytest.approx(-10.0)
    # Loan payment from the bank reduces the loan
    assert liabs["Long-Term Debt"]["amount"] == pytest.approx(-185.0)
    # Both halves of the Truist payment loaded → nothing left in transit, except the
    # Elan payment whose bank side is missing
    clearing = next(x for x in bs["liabilities"] if x["code"] == CLEARING_CODE)
    assert clearing["amount"] == pytest.approx(50.0)
    assert equity["Owner's Draws"]["amount"] == pytest.approx(-40.0)
    assert equity["Net Income"]["amount"] == pytest.approx(700.0)
    assert bs["balanced"] is True
    assert bs["imbalance"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_pnl_is_unchanged_by_statement_accounts() -> None:
    pnl = (await _bundle()).pnl
    assert pnl["totalRevenue"] == pytest.approx(1000.0)
    assert pnl["totalExpenses"] == pytest.approx(300.0)
    assert {i["code"] for i in pnl["expenseItems"]} == {"6050"}
