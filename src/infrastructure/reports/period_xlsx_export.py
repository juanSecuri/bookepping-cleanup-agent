"""Export period financial statements to a simple openpyxl workbook ($0)."""
from __future__ import annotations

from io import BytesIO

import openpyxl
from openpyxl.styles import Font

from src.use_cases.emit_period_reports import PeriodFinancialBundle


def bundle_to_xlsx_bytes(bundle: PeriodFinancialBundle) -> bytes:
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "P&L"
    ws.append(["LedgerAI — Estado de resultados", bundle.period_label])
    ws.append(["Motor", bundle.engine])
    ws.append([])
    ws.append(["Ingresos", bundle.pnl.get("totalRevenue") or bundle.pnl.get("revenue")])
    ws.append(["Gastos", bundle.pnl.get("totalExpenses") or bundle.pnl.get("expenses")])
    ws.append(["Utilidad neta", bundle.pnl.get("netIncome") or bundle.pnl.get("net_income")])
    ws.append([])
    ws.append(["Código", "Cuenta", "Monto", "Txs", "Tipo"])
    for row in bundle.pnl.get("revenueItems") or []:
        ws.append([row.get("code"), row.get("name"), row.get("amount"), row.get("txCount"), "revenue"])
    for row in bundle.pnl.get("expenseItems") or []:
        ws.append([row.get("code"), row.get("name"), row.get("amount"), row.get("txCount"), "expense"])
    ws["A1"].font = Font(bold=True, size=14)

    bs = wb.create_sheet("Balance")
    bal = bundle.balance_sheet or {}
    bs.append(["LedgerAI — Balance", bundle.period_label])
    bs.append(["Cuadra", bal.get("balanced")])
    bs.append(["Descuadre", bal.get("imbalance")])
    bs.append([])
    bs.append(["Sección", "Código", "Nombre", "Monto"])
    for section, key in (("Activo", "assets"), ("Pasivo", "liabilities"), ("Patrimonio", "equity")):
        for row in bal.get(key) or []:
            bs.append([section, row.get("code"), row.get("name"), row.get("amount")])
    bs.append([])
    bs.append(["Total activos", bal.get("totalAssets")])
    bs.append(["Total pasivos", bal.get("totalLiabilities")])
    bs.append(["Total patrimonio", bal.get("totalEquity")])
    bs["A1"].font = Font(bold=True, size=14)

    cf = wb.create_sheet("Cash flow")
    flow = bundle.cash_flow or {}
    cf.append(["LedgerAI — Cash flow O/I/F", bundle.period_label])
    cf.append(["Tipo", "Entradas", "Salidas", "Neto"])
    for label, key in (("Operativo", "operating"), ("Inversión", "investing"), ("Financiación", "financing")):
        block = flow.get(key) or {}
        cf.append([label, block.get("inflows"), block.get("outflows"), block.get("net")])
    cf.append(["Cambio neto", "", "", flow.get("netChange")])
    cf["A1"].font = Font(bold=True, size=14)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
