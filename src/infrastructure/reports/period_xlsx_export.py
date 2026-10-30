"""Export the period CPA package to an openpyxl workbook ($0) — 4 sheets."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.infrastructure.reports.qb_layout import basis_footer, build_qb_reports
from src.infrastructure.reports.qb_xlsx import write_qb_sheet
from src.use_cases.emit_period_reports import PeriodFinancialBundle

HEADER_FILL = PatternFill("solid", fgColor="1A4032")
HEADER_FONT = Font(bold=True, color="E8DCC8")
TOTAL_FONT = Font(bold=True)
NEG_FONT = Font(color="F87171")
TITLE_FONT = Font(bold=True, size=14, color="1A4032")


def _money_cell(ws, row: int, col: int, value: float | None) -> None:
    v = float(value or 0)
    cell = ws.cell(row=row, column=col, value=v)
    cell.number_format = '"$"#,##0.00'
    if v < 0:
        cell.font = NEG_FONT


def _style_header_row(ws, row: int, cols: int) -> None:
    for c in range(1, cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center")


def bundle_to_xlsx_bytes(
    bundle: PeriodFinancialBundle,
    transactions: list[Any] | None = None,
    *,
    company_name: str = "LedgerAI",
) -> bytes:
    """CPA package: P&L + Balance Sheet (QuickBooks layout) + Cash Flow + Transactions."""
    wb = openpyxl.Workbook()
    footer = basis_footer()
    qb = build_qb_reports(bundle, company_name)
    first = True
    for key in ("profit_and_loss", "balance_sheet"):
        report = qb[key]
        ws = wb.active if first else wb.create_sheet()
        ws.title = report["title"][:31]
        first = False
        write_qb_sheet(
            ws,
            company=company_name,
            title=report["title"],
            period=report["period"],
            rows=report["rows"],
            footer=footer,
        )

    # ── Cash flow ──────────────────────────────────────────────────────────
    cf = wb.create_sheet("Cash Flow")
    flow = bundle.cash_flow or {}
    detail = bundle.cash_flow_detail or {}
    cf.append(["LedgerAI — Cash flow O/I/F", bundle.period_label])
    cf["A1"].font = TITLE_FONT
    cf.append([])
    cf.append(["Tipo", "Código", "Cuenta", "Monto", "# txs"])
    _style_header_row(cf, 3, 5)
    row_i = 4
    for label, key, sub_key in (
        ("OPERATIVO", "operating", "operatingSubtotal"),
        ("INVERSIÓN", "investing", "investingSubtotal"),
        ("FINANCIACIÓN", "financing", "financingSubtotal"),
    ):
        lines = detail.get(key) or []
        if not lines:
            cf.cell(row=row_i, column=1, value=label)
            _money_cell(
                cf,
                row_i,
                4,
                float(detail.get(sub_key) or (flow.get(key) or {}).get("net") or 0),
            )
            row_i += 1
        else:
            for item in lines:
                cf.cell(row=row_i, column=1, value=label)
                cf.cell(row=row_i, column=2, value=item.get("code"))
                cf.cell(row=row_i, column=3, value=item.get("name"))
                _money_cell(cf, row_i, 4, float(item.get("amount") or 0))
                cf.cell(row=row_i, column=5, value=item.get("txCount"))
                row_i += 1
        cf.cell(row=row_i, column=3, value=f"SUBTOTAL {label}").font = TOTAL_FONT
        _money_cell(
            cf,
            row_i,
            4,
            float(detail.get(sub_key) or (flow.get(key) or {}).get("net") or 0),
        )
        cf.cell(row=row_i, column=4).font = TOTAL_FONT
        row_i += 2
    cf.cell(row=row_i, column=3, value="FLUJO NETO TOTAL").font = TOTAL_FONT
    _money_cell(cf, row_i, 4, float(detail.get("netTotal") or flow.get("netChange") or 0))
    cf.cell(row=row_i, column=4).font = TOTAL_FONT

    # ── Transacciones ──────────────────────────────────────────────────────
    tx = wb.create_sheet("Transacciones")
    tx.append(["LedgerAI — Transacciones del periodo", bundle.period_label])
    tx["A1"].font = TITLE_FONT
    tx.append([])
    tx.append(["Fecha", "Descripción", "Cuenta", "Código", "Tipo", "Monto", "Estado"])
    _style_header_row(tx, 3, 7)
    row_i = 4
    for t in transactions or []:
        d = str(getattr(t, "transaction_date", "") or "")
        if bundle.date_from and d and d < bundle.date_from:
            continue
        if bundle.date_to and d and d > bundle.date_to:
            continue
        status = getattr(t, "status", None)
        status_s = status.value if hasattr(status, "value") else str(status or "")
        if status_s not in ("verified", "closed"):
            continue
        tx_type = getattr(t, "transaction_type", None)
        type_s = tx_type.value if hasattr(tx_type, "value") else str(tx_type or "")
        tx.cell(row=row_i, column=1, value=d)
        tx.cell(row=row_i, column=2, value=getattr(t, "description", "") or "")
        tx.cell(row=row_i, column=3, value=getattr(t, "chart_of_accounts_name", "") or "")
        tx.cell(row=row_i, column=4, value=getattr(t, "chart_of_accounts_code", "") or "")
        tx.cell(row=row_i, column=5, value=type_s)
        _money_cell(tx, row_i, 6, float(getattr(t, "amount", 0) or 0))
        tx.cell(row=row_i, column=7, value=status_s)
        row_i += 1
    if row_i == 4:
        tx.cell(row=4, column=1, value="(Sin txs verificadas en el periodo)")

    for sheet in (cf, tx):
        for col in range(1, 8):
            sheet.column_dimensions[get_column_letter(col)].width = 14
        sheet.column_dimensions["B"].width = 28
        sheet.column_dimensions["C"].width = 28

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
