"""API: QuickBooks reports in /reports/statements + per-report Excel downloads."""

from __future__ import annotations

from io import BytesIO

import openpyxl
import pytest
from fastapi.testclient import TestClient

import apps.api.main as main
from tests.unit.test_qb_report_layout import _bundle

WID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def fake_bundle(_workspace_id: str, **kw):
        kw = {k: v for k, v in kw.items() if v is not None}
        return await _bundle(**kw)

    async def fake_company(_workspace_id: str) -> str:
        return "My Xcell Network CORP"

    class _NoAlerts:
        def list_alerts(self, _tid):
            return []

    monkeypatch.setattr(main, "_period_bundle", fake_bundle)
    monkeypatch.setattr(main, "_company_name", fake_company)
    monkeypatch.setattr(main, "StatementPeriodRepository", _NoAlerts)
    return TestClient(main.app)


def test_statements_include_quickbooks_reports(client: TestClient) -> None:
    res = client.get("/api/reports/statements", params={"workspace_id": WID, "fiscal_year": "2025"})
    assert res.status_code == 200
    qb = res.json()["qb"]
    assert qb["company"] == "My Xcell Network CORP"
    assert qb["profit_and_loss"]["period"] == "January-December, 2025"
    assert qb["balance_sheet"]["period"] == "As of Dec 31, 2025"
    assert qb["profit_and_loss"]["rows"][-1]["label"] == "Net Income"
    assert qb["balance_sheet"]["rows"][-1]["label"] == "Total Liabilities and Equity"


@pytest.mark.parametrize(
    ("slug", "title"),
    [("profit-and-loss", "Profit and Loss"), ("balance-sheet", "Balance Sheet")],
)
def test_download_single_report_xlsx(client: TestClient, slug: str, title: str) -> None:
    res = client.get(
        f"/api/reports/qb/{slug}.xlsx", params={"workspace_id": WID, "fiscal_year": "2025"}
    )
    assert res.status_code == 200
    assert "attachment" in res.headers["content-disposition"]
    assert "My_Xcell_Network_CORP" in res.headers["content-disposition"]
    ws = openpyxl.load_workbook(BytesIO(res.content)).active
    assert ws["A1"].value == "My Xcell Network CORP"
    assert ws["A2"].value == title


def test_unknown_report_is_404(client: TestClient) -> None:
    res = client.get("/api/reports/qb/cash.xlsx", params={"workspace_id": WID})
    assert res.status_code == 404
