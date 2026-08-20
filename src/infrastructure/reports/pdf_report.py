"""
PDF report generator for financial statements.

Uses reportlab to produce professional PDF reports with:
  - Header with company/period info
  - Income Statement table
  - Balance Sheet table
  - Page numbers and footer

Install: pip install reportlab
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.domain.models.financial_statement import BalanceSheet, IncomeStatement

# ── Colour palette ────────────────────────────────────────────────────────────
_NAVY = colors.HexColor("#1F3864")
_BLUE = colors.HexColor("#2E75B6")
_LIGHT_BLUE = colors.HexColor("#D6E4F0")
_GREEN = colors.HexColor("#1A7A1A")
_RED = colors.HexColor("#C00000")
_WHITE = colors.white
_LIGHT_GREY = colors.HexColor("#F5F5F5")


def _fmt(amount: Decimal, currency: str = "USD") -> str:
    sign = "-" if amount < 0 else ""
    abs_val = abs(amount)
    return f"{sign}{currency} {abs_val:,.2f}"


def _table_style_base() -> list:
    return [
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _LIGHT_GREY]),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]


def _build_income_statement_table(stmt: IncomeStatement) -> list:
    styles = getSampleStyleSheet()
    bold_style = ParagraphStyle("bold", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10)
    section_style = ParagraphStyle("section", parent=styles["Normal"], fontName="Helvetica-Bold",
                                   fontSize=9, textColor=_WHITE)

    def section_row(label: str) -> list:
        return [Paragraph(label, section_style), "", ""]

    def data_row(name: str, code: str, amount: Decimal) -> list:
        color = _GREEN if amount >= 0 else _RED
        amt_para = Paragraph(f'<font color="{color.hexval()}">{_fmt(amount, stmt.currency)}</font>',
                             styles["Normal"])
        return [f"   {name}", code, amt_para]

    def subtotal_row(label: str, amount: Decimal) -> list:
        color = _GREEN if amount >= 0 else _RED
        return [Paragraph(f"<b>{label}</b>", bold_style), "",
                Paragraph(f'<b><font color="{color.hexval()}">{_fmt(amount, stmt.currency)}</font></b>', bold_style)]

    rows = [["Cuenta", "Código", "Monto"]]

    rows.append(section_row("INGRESOS"))
    for line in stmt.revenue_lines:
        rows.append(data_row(line.account_name, line.account_code, line.amount))
    rows.append(subtotal_row("Total Ingresos", stmt.total_revenue))

    rows.append(section_row("COSTO DE VENTAS"))
    for line in stmt.cogs_lines:
        rows.append(data_row(line.account_name, line.account_code, line.amount))
    rows.append(subtotal_row("Total Costo de Ventas", stmt.total_cogs))
    rows.append(subtotal_row("UTILIDAD BRUTA", stmt.gross_profit))

    rows.append(section_row("GASTOS OPERACIONALES"))
    for line in stmt.expense_lines:
        rows.append(data_row(line.account_name, line.account_code, line.amount))
    rows.append(subtotal_row("Total Gastos", stmt.total_expenses))

    rows.append(["", "", ""])
    rows.append(subtotal_row("✦ UTILIDAD NETA DEL PERÍODO", stmt.net_income))

    col_widths = [3.8 * inch, 1.0 * inch, 1.8 * inch]
    t = Table(rows, colWidths=col_widths, repeatRows=1)

    style = _table_style_base()
    # Colour section header rows
    section_indices = [i for i, r in enumerate(rows) if isinstance(r[0], Paragraph)
                       and r[0].style.name == "section"]
    for idx in section_indices:
        style.append(("BACKGROUND", (0, idx), (-1, idx), _BLUE))
        style.append(("SPAN", (0, idx), (-1, idx)))

    t.setStyle(TableStyle(style))
    return [t]


def _build_balance_sheet_table(bs: BalanceSheet) -> list:
    styles = getSampleStyleSheet()
    bold_style = ParagraphStyle("bold", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10)
    section_style = ParagraphStyle("section", parent=styles["Normal"], fontName="Helvetica-Bold",
                                   fontSize=9, textColor=_WHITE)

    def section_row(label: str) -> list:
        return [Paragraph(label, section_style), "", ""]

    def data_row(name: str, code: str, amount: Decimal) -> list:
        return [f"   {name}", code, _fmt(amount, bs.currency)]

    def subtotal_row(label: str, amount: Decimal) -> list:
        return [Paragraph(f"<b>{label}</b>", bold_style), "",
                Paragraph(f"<b>{_fmt(amount, bs.currency)}</b>", bold_style)]

    rows = [["Cuenta", "Código", "Monto"]]

    rows.append(section_row("ACTIVOS"))
    for line in bs.assets.lines:
        rows.append(data_row(line.account_name, line.account_code, line.amount))
    rows.append(subtotal_row("Total Activos", bs.assets.total))

    rows.append(section_row("PASIVOS"))
    for line in bs.liabilities.lines:
        rows.append(data_row(line.account_name, line.account_code, line.amount))
    rows.append(subtotal_row("Total Pasivos", bs.liabilities.total))

    rows.append(section_row("PATRIMONIO"))
    for line in bs.equity.lines:
        rows.append(data_row(line.account_name, line.account_code, line.amount))
    rows.append(data_row("Utilidades Retenidas Períodos Anteriores", "", bs.retained_earnings))
    rows.append(data_row("Utilidad del Período Actual", "", bs.current_period_net_income))
    rows.append(subtotal_row("Total Patrimonio",
                             bs.equity.total + bs.retained_earnings + bs.current_period_net_income))

    rows.append(["", "", ""])
    balanced = "✓ ECUACIÓN CUADRA" if bs.is_balanced else "✗ ECUACIÓN NO CUADRA"
    rows.append(subtotal_row(f"TOTAL PASIVOS + PATRIMONIO  ({balanced})",
                             bs.total_liabilities_and_equity))

    col_widths = [3.8 * inch, 1.0 * inch, 1.8 * inch]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(_table_style_base()))
    return [t]


def generate_pdf_report(
    income_stmt: IncomeStatement,
    balance_sheet: BalanceSheet,
    output_path: Path,
    company_name: str = "Empresa",
) -> Path:
    """
    Generate a professional PDF with both financial statements.

    Args:
        income_stmt:   IncomeStatement domain entity
        balance_sheet: BalanceSheet domain entity
        output_path:   Where to save the PDF
        company_name:  Shown in the document header

    Returns:
        Path to the saved PDF
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Title"], fontSize=16,
                                 textColor=_NAVY, spaceAfter=6)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"], fontSize=11,
                                    textColor=_BLUE, spaceAfter=12)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=1 * inch,
        bottomMargin=0.75 * inch,
    )

    story = []

    # ── Income Statement ──────────────────────────────────────────────────────
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(f"Estado de Resultados — {income_stmt.period_label}", subtitle_style))
    story.extend(_build_income_statement_table(income_stmt))
    story.append(PageBreak())

    # ── Balance Sheet ─────────────────────────────────────────────────────────
    story.append(Paragraph(company_name, title_style))
    story.append(Paragraph(f"Balance General — {balance_sheet.period_label}", subtitle_style))
    story.extend(_build_balance_sheet_table(balance_sheet))

    doc.build(story)
    return output_path
