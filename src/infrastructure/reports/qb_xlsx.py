"""Write QuickBooks-layout reports to Excel, matching the TPC template workbooks.

Layout (same as a QuickBooks Online export):

    A1  Company name
    A2  Report title            (Profit and Loss / Balance Sheet)
    A3  Period                  (January-December, 2025 / As of Dec 31, 2025)
    B5  Total
    A6… report rows; totals are live formulas over their child rows
    footer  "Cash Basis <timestamp>"
"""

from __future__ import annotations

from io import BytesIO

import openpyxl
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.worksheet.worksheet import Worksheet

MONEY = "#,##0.00;-#,##0.00"
_FIRST_ROW = 6
_TOP = Border(top=Side(style="thin"))
_DOUBLE = Border(top=Side(style="thin"), bottom=Side(style="double"))


def _formula(refs: list[str], signs: list[int] | None = None) -> str | int:
    if not refs:
        return 0
    signs = signs or [1] * len(refs)
    parts = [
        ("" if i == 0 and s > 0 else "+" if s > 0 else "-") + r
        for i, (r, s) in enumerate(zip(refs, signs, strict=True))
    ]
    return "=" + "".join(parts)


def write_qb_sheet(
    ws: Worksheet,
    *,
    company: str,
    title: str,
    period: str,
    rows: list[dict],
    footer: str,
) -> None:
    ws["A1"] = company
    ws["A2"] = title
    ws["A3"] = period
    for cell, size in (("A1", 12), ("A2", 14), ("A3", 10)):
        ws[cell].font = Font(bold=cell != "A3", size=size)
        ws[cell].alignment = Alignment(horizontal="center")
    ws.merge_cells("A1:B1")
    ws.merge_cells("A2:B2")
    ws.merge_cells("A3:B3")
    ws["A5"] = ""
    ws["B5"] = "Total"
    ws["B5"].font = Font(bold=True)
    ws["B5"].alignment = Alignment(horizontal="right")
    ws["B5"].border = Border(bottom=Side(style="thin"))

    def ref(i: int) -> str:
        return f"B{_FIRST_ROW + i}"

    last_index = len(rows) - 1
    for i, row in enumerate(rows):
        r = _FIRST_ROW + i
        kind = row["kind"]
        label = ws.cell(row=r, column=1, value=row["label"])
        label.alignment = Alignment(horizontal="left", indent=int(row.get("depth") or 0) * 2)
        if kind == "header":
            continue
        if kind == "account":
            value: float | str | int = round(float(row["amount"] or 0), 2)
        elif kind == "total":
            value = _formula([ref(c) for c in row.get("sumOf") or []])
        else:  # summary
            terms = row.get("terms") or []
            value = _formula([ref(t[1]) for t in terms], [t[0] for t in terms])
        cell = ws.cell(row=r, column=2, value=value)
        cell.number_format = MONEY
        if kind in {"total", "summary"}:
            label.font = Font(bold=True)
            cell.font = Font(bold=True)
            cell.border = _DOUBLE if i == last_index else _TOP

    ws.cell(row=_FIRST_ROW + len(rows) + 3, column=1, value=footer).font = Font(italic=True, size=9)
    ws.column_dimensions["A"].width = 52
    ws.column_dimensions["B"].width = 16
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A6"


def report_xlsx_bytes(*, company: str, report: dict, footer: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report["title"][:31]
    write_qb_sheet(
        ws,
        company=company,
        title=report["title"],
        period=report["period"],
        rows=report["rows"],
        footer=footer,
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
