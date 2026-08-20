"""
FastAPI application — Bookkeeping Clean-up Agent  v0.3.0

Endpoints
─────────
  GET  /                            Serve HTML SPA (index.html)
  GET  /health                      Liveness probe
  POST /ingest                      Upload receipt photo, voice note, or invoice PDF
  POST /statements                  Upload bank-statement PDF → full pipeline
  GET  /transactions                List transactions for a tenant
  PATCH /transactions/{id}          Update account categorisation + mark verified
  GET  /movements                   List bank movements for a tenant
  POST /periods/{period}/close      Close a fiscal period → MonthlyLedger
  POST /periods/{period}/report     Generate Excel + PDF financial statements
  GET  /periods                     List all periods (open + closed) for a tenant

  ── Fase 2 (QuickBooks) ──────────────────────────────────────────────────
  GET  /qb/connect                  [FASE 2] OAuth2 redirect to QuickBooks
  GET  /qb/callback                 [FASE 2] OAuth2 callback + token storage
  POST /qb/export/{period}          [FASE 2] Export closed period to QuickBooks
"""
from __future__ import annotations

import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.use_cases.close_period import ClosePeriodUseCase, PeriodAlreadyClosedError
from src.use_cases.generate_financial_statements import GenerateFinancialStatementsUseCase
from src.use_cases.ingest_document import IngestDocumentUseCase
from src.use_cases.process_statement import ProcessStatementUseCase
from src.infrastructure.repositories.transaction_repository import TransactionRepository
from src.infrastructure.repositories.bank_movement_repository import BankMovementRepository
from src.infrastructure.repositories.monthly_ledger_repository import MonthlyLedgerRepository
from src.infrastructure.reports.excel_report import generate_excel_report
from src.infrastructure.reports.pdf_report import generate_pdf_report

# ── paths ────────────────────────────────────────────────────────────────────
_UI_DIR = Path(__file__).parent.parent / "ui"
_UI_INDEX = _UI_DIR / "index.html"

# ── app factory ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Bookkeeping Clean-up Agent",
    version="0.3.0",
    description=(
        "AI-powered pipeline to reconstruct up to 10 years of unstructured bookkeeping. "
        "Generates Balance Sheet (Balance General) and Income Statement (Estado de Resultados) "
        "per period directly — no accounting software required. "
        "QuickBooks integration: Fase 2 (pendiente)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── request / response schemas ───────────────────────────────────────────────

class TransactionPatch(BaseModel):
    """Body for PATCH /transactions/{id}"""
    chart_of_accounts_code: str | None = None
    chart_of_accounts_name: str | None = None
    account_type: str | None = None        # AccountType value
    description: str | None = None
    verify: bool = False                   # if True → move status to 'verified'


# ─────────────────────────────────────────────────────────────────────────────
# SPA  — serve the HTML front-end
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def spa_root() -> HTMLResponse:
    """Serve the single-page application."""
    if not _UI_INDEX.exists():
        raise HTTPException(status_code=404, detail="UI not found. Run from project root.")
    return HTMLResponse(content=_UI_INDEX.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.3.0"}


# ─────────────────────────────────────────────────────────────────────────────
# Document ingestion
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
) -> dict:
    """
    Upload a receipt photo (JPG/PNG), voice note (MP3/WAV/M4A),
    or invoice PDF for AI extraction → persisted as FinancialTransaction.
    """
    tid = uuid.UUID(tenant_id)
    suffix = Path(file.filename or "upload").suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        result = await IngestDocumentUseCase().execute(tmp_path, tid)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    if isinstance(result, list):
        return {"type": "bank_movements", "count": len(result)}
    return {"type": "transaction", "data": result.model_dump(mode="json")}


# ─────────────────────────────────────────────────────────────────────────────
# Bank statement pipeline
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/statements")
async def process_statement(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    bank_name: str = Form(...),
    bank_account_number: str = Form(...),
    statement_month: str = Form(...),
) -> dict:
    """
    Upload a bank statement PDF.
    Pipeline: LlamaParse extraction → RAG categorisation → reconciliation.
    Returns a processing report.
    """
    tid = uuid.UUID(tenant_id)
    with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        report = await ProcessStatementUseCase().execute(
            tmp_path, tid, bank_name, bank_account_number, statement_month
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "total_movements": report.total_movements,
        "categorised": report.categorised,
        "reconciled": report.reconciled,
        "unmatched": report.unmatched,
        "ambiguous": report.ambiguous,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Transactions
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/transactions")
async def list_transactions(
    tenant_id: str,
    status: str | None = None,
    fiscal_period: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    Return paginated transactions for a tenant.

    Query params:
      tenant_id     UUID (required)
      status        pending_review | verified | closed  (optional filter)
      fiscal_period YYYY-MM  (optional filter)
      limit         default 100
      offset        default 0
    """
    tid = uuid.UUID(tenant_id)
    repo = TransactionRepository()

    if status == "pending_review":
        transactions = await repo.list_pending(tid)
        # Apply fiscal_period filter client-side if needed
        if fiscal_period:
            transactions = [t for t in transactions if t.fiscal_period == fiscal_period]
        total = len(transactions)
        page = transactions[offset : offset + limit]
    else:
        page = await repo.list_by_tenant(tid, limit=limit, offset=offset)
        if status:
            page = [t for t in page if t.status.value == status]
        if fiscal_period:
            page = [t for t in page if t.fiscal_period == fiscal_period]
        total = len(page)

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [t.model_dump(mode="json") for t in page],
    }


@app.patch("/transactions/{transaction_id}")
async def patch_transaction(
    transaction_id: str,
    body: TransactionPatch,
    tenant_id: str,
) -> dict:
    """
    Update account categorisation for a transaction and optionally verify it.

    - Supply chart_of_accounts_code + chart_of_accounts_name to re-categorise.
    - Set verify=true to move status from pending_review → verified.
    """
    tid = uuid.UUID(tenant_id)
    txn_id = uuid.UUID(transaction_id)

    repo = TransactionRepository()
    txn = await repo.get_by_id(txn_id)
    if txn is None or txn.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Apply updates (immutable model → produce new instance)
    updates: dict = {}
    if body.chart_of_accounts_code is not None:
        updates["chart_of_accounts_code"] = body.chart_of_accounts_code
    if body.chart_of_accounts_name is not None:
        updates["chart_of_accounts_name"] = body.chart_of_accounts_name
    if body.description is not None:
        updates["description"] = body.description

    if updates:
        txn = txn.model_copy(update=updates)

    if body.verify and txn.chart_of_accounts_code:
        txn = txn.mark_verified(
            txn.chart_of_accounts_code,
            txn.chart_of_accounts_name or "",
            txn.category_confidence or 1.0,
        )

    saved = await repo.save(txn)
    return {"data": saved.model_dump(mode="json")}


# ─────────────────────────────────────────────────────────────────────────────
# Bank movements
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/movements")
async def list_movements(
    tenant_id: str,
    statement_month: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """
    Return bank movements for a tenant.

    Query params:
      tenant_id       UUID (required)
      statement_month YYYY-MM (optional filter)
      status          pending_review | verified | closed (optional filter)
      limit           default 200
      offset          default 0
    """
    tid = uuid.UUID(tenant_id)
    repo = BankMovementRepository()

    if statement_month:
        movements = await repo.list_by_period(tid, statement_month)
    else:
        movements = await repo.list_by_tenant(tid, limit=limit, offset=offset)

    if status:
        movements = [m for m in movements if m.status.value == status]

    page = movements[offset : offset + limit]
    return {
        "total": len(movements),
        "limit": limit,
        "offset": offset,
        "items": [m.model_dump(mode="json") for m in page],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Periods
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/periods")
async def list_periods(tenant_id: str) -> dict:
    """
    Return all MonthlyLedgers for a tenant (open + closed), sorted by period.
    Useful for rendering the 12-month period grid in the UI.
    """
    tid = uuid.UUID(tenant_id)
    repo = MonthlyLedgerRepository()
    ledgers = await repo.list_by_tenant(tid, limit=120)   # up to 10 years
    return {
        "total": len(ledgers),
        "items": [
            {
                "id": str(l.id),
                "fiscal_period": l.fiscal_period,
                "status": l.status,
                "transaction_count": l.transaction_count,
                "net_income": str(l.net_income),
                "total_assets": str(l.total_assets),
                "total_liabilities": str(l.total_liabilities),
                "total_equity": str(l.total_equity),
                "closed_at": l.closed_at.isoformat() if l.closed_at else None,
            }
            for l in ledgers
        ],
    }


@app.post("/periods/{fiscal_period}/close")
async def close_period(
    fiscal_period: str,
    tenant_id: str = Form(...),
) -> dict:
    """
    Close a fiscal period.

    Aggregates all VERIFIED transactions for tenant + period into a
    MonthlyLedger and marks them as CLOSED.  Idempotent check: raises 409
    if the period is already closed.
    """
    tid = uuid.UUID(tenant_id)
    try:
        ledger = await ClosePeriodUseCase().execute(tid, fiscal_period)
    except PeriodAlreadyClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "fiscal_period": ledger.fiscal_period,
        "status": ledger.status,
        "transaction_count": ledger.transaction_count,
        "net_income": str(ledger.net_income),
        "total_assets": str(ledger.total_assets),
        "total_liabilities": str(ledger.total_liabilities),
        "total_equity": str(ledger.total_equity),
    }


@app.post("/periods/{fiscal_period}/report")
async def generate_report(
    fiscal_period: str,
    tenant_id: str = Form(...),
    company_name: str = Form(default="Empresa"),
    format: str = Form(default="excel"),
) -> FileResponse:
    """
    Generate financial statements (Balance General + Estado de Resultados)
    for a closed period.

    format: 'excel' | 'pdf'

    Returns the file for immediate download.
    """
    tid = uuid.UUID(tenant_id)

    # Load the closed MonthlyLedger from the database
    ledger_repo = MonthlyLedgerRepository()
    ledger = await ledger_repo.get_by_period(tid, fiscal_period)
    if ledger is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ledger found for period {fiscal_period}. Close the period first.",
        )
    if ledger.status != "closed":
        raise HTTPException(
            status_code=409,
            detail=f"Period {fiscal_period} is not yet closed (status={ledger.status}).",
        )

    # Build financial statements from the ledger
    stmt_use_case = GenerateFinancialStatementsUseCase()
    income_stmt, balance_sheet = stmt_use_case.from_ledger(ledger, company_name)

    # Generate the requested file format
    import tempfile, os
    tmp_dir = tempfile.mkdtemp()

    if format == "pdf":
        out_path = Path(tmp_dir) / f"estados_financieros_{fiscal_period}.pdf"
        generate_pdf_report(income_stmt, balance_sheet, str(out_path))
        media_type = "application/pdf"
    else:
        out_path = Path(tmp_dir) / f"estados_financieros_{fiscal_period}.xlsx"
        generate_excel_report(income_stmt, balance_sheet, str(out_path))
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return FileResponse(
        path=str(out_path),
        media_type=media_type,
        filename=out_path.name,
        background=None,    # file cleaned up by OS temp dir rotation
    )


# ─────────────────────────────────────────────────────────────────────────────
# FASE 2 — QuickBooks  (stubs — DO NOT ACTIVATE until all periods are CLOSED)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/qb/connect", include_in_schema=False)
async def qb_connect() -> dict:
    """
    FASE 2 — QuickBooks OAuth2 initiation.
    Precondición: todos los períodos históricos deben estar en status CLOSED.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "FASE 2 — QuickBooks integration not yet active. "
            "Complete and close all historical periods first."
        ),
    )


@app.get("/qb/callback", include_in_schema=False)
async def qb_callback() -> dict:
    """FASE 2 — QuickBooks OAuth2 callback."""
    raise HTTPException(status_code=501, detail="FASE 2 — QuickBooks integration not yet active.")


@app.post("/qb/export/{fiscal_period}", include_in_schema=False)
async def qb_export(fiscal_period: str, tenant_id: str = Form(...)) -> dict:
    """FASE 2 — Export a closed period's transactions to QuickBooks."""
    raise HTTPException(status_code=501, detail="FASE 2 — QuickBooks integration not yet active.")
