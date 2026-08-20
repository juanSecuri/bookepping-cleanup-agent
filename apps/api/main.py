"""
FastAPI application — Bookkeeping Clean-up Agent.
Thin HTTP layer; business logic lives in use-cases via AppContainer.
"""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from src.config import get_settings
from src.container import get_container
from src.domain.exceptions import BookkeepingError
from src.infrastructure.reports.excel_report import generate_excel_report
from src.infrastructure.reports.pdf_report import generate_pdf_report
from src.use_cases.close_period import PeriodAlreadyClosedError

_UI_DIR = Path(__file__).parent.parent / "ui"
_UI_INDEX = _UI_DIR / "index.html"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    key = settings.supabase_service_role_key.get_secret_value()
    if key.startswith("PENDIENTE") or len(key) < 20:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is missing. Copy the service_role secret from "
            "https://supabase.com/dashboard/project/jhzhxxkvyicwkzrqrevm/settings/api "
            "into your .env file (not the anon/publishable key)."
        )
    yield


app = FastAPI(
    title="Bookkeeping Clean-up Agent",
    version="0.4.0",
    description=(
        "AI-powered pipeline to reconstruct unstructured bookkeeping with OpenAI. "
        "Generates Balance Sheet and Income Statement per period. "
        "QuickBooks integration: Fase 2 (pendiente)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TransactionPatch(BaseModel):
    chart_of_accounts_code: str | None = None
    chart_of_accounts_name: str | None = None
    description: str | None = None
    verify: bool = False


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def spa_root() -> HTMLResponse:
    if not _UI_INDEX.exists():
        raise HTTPException(status_code=404, detail="UI not found. Run from project root.")
    return HTMLResponse(content=_UI_INDEX.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.4.0", "llm": "openai"}


@app.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
) -> dict:
    container = get_container()
    tid = uuid.UUID(tenant_id)
    suffix = Path(file.filename or "upload").suffix
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        result = await container.ingest.execute(tmp_path, tid)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    if isinstance(result, list):
        return {"type": "bank_movements", "count": len(result)}
    return {"type": "transaction", "data": result.model_dump(mode="json")}


@app.post("/statements")
async def process_statement(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    bank_name: str = Form(...),
    bank_account_number: str = Form(...),
    statement_month: str = Form(...),
) -> dict:
    container = get_container()
    tid = uuid.UUID(tenant_id)
    with NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        report = await container.process_statement.execute(
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


@app.get("/transactions")
async def list_transactions(
    tenant_id: str,
    status: str | None = None,
    fiscal_period: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    container = get_container()
    tid = uuid.UUID(tenant_id)

    if status == "pending_review":
        transactions = await container.transactions.list_pending(tid)
    else:
        transactions = await container.transactions.list_by_tenant(
            tid, limit=max(limit + offset, 100), offset=0
        )

    if status and status != "pending_review":
        transactions = [t for t in transactions if t.status.value == status]
    if fiscal_period:
        transactions = [t for t in transactions if t.fiscal_period == fiscal_period]

    total = len(transactions)
    page = transactions[offset : offset + limit]
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
    container = get_container()
    tid = uuid.UUID(tenant_id)
    txn_id = uuid.UUID(transaction_id)

    txn = await container.transactions.get_by_id(txn_id)
    if txn is None or txn.tenant_id != tid:
        raise HTTPException(status_code=404, detail="Transaction not found")

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

    saved = await container.transactions.save(txn)
    return {"data": saved.model_dump(mode="json")}


@app.get("/movements")
async def list_movements(
    tenant_id: str,
    statement_month: str | None = None,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    container = get_container()
    tid = uuid.UUID(tenant_id)

    if statement_month:
        movements = await container.movements.list_by_period(tid, statement_month)
    else:
        movements = await container.movements.list_by_tenant(tid, limit=limit, offset=offset)

    if status:
        movements = [m for m in movements if m.status.value == status]

    page = movements[offset : offset + limit]
    return {
        "total": len(movements),
        "limit": limit,
        "offset": offset,
        "items": [m.model_dump(mode="json") for m in page],
    }


@app.get("/periods")
async def list_periods(tenant_id: str) -> dict:
    container = get_container()
    tid = uuid.UUID(tenant_id)
    ledgers = await container.ledgers.list_by_tenant(tid, limit=120)
    return {
        "total": len(ledgers),
        "items": [
            {
                "id": str(ledger.id),
                "fiscal_period": ledger.fiscal_period,
                "status": ledger.status,
                "transaction_count": ledger.transaction_count,
                "net_income": str(ledger.net_income),
                "total_assets": str(ledger.total_assets),
                "total_liabilities": str(ledger.total_liabilities),
                "total_equity": str(ledger.total_equity),
                "closed_at": ledger.closed_at.isoformat() if ledger.closed_at else None,
            }
            for ledger in ledgers
        ],
    }


@app.post("/periods/{fiscal_period}/close")
async def close_period(fiscal_period: str, tenant_id: str = Form(...)) -> dict:
    container = get_container()
    tid = uuid.UUID(tenant_id)
    try:
        ledger = await container.close_period.execute(tid, fiscal_period)
    except PeriodAlreadyClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BookkeepingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    container = get_container()
    tid = uuid.UUID(tenant_id)

    ledger = await container.ledgers.get_by_period(tid, fiscal_period)
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

    income_stmt, balance_sheet = container.statements.from_ledger(ledger, company_name)
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
    )


@app.get("/qb/connect", include_in_schema=False)
async def qb_connect() -> dict:
    raise HTTPException(
        status_code=501,
        detail="FASE 2 — QuickBooks integration not yet active.",
    )


@app.get("/qb/callback", include_in_schema=False)
async def qb_callback() -> dict:
    raise HTTPException(status_code=501, detail="FASE 2 — QuickBooks integration not yet active.")


@app.post("/qb/export/{fiscal_period}", include_in_schema=False)
async def qb_export(fiscal_period: str, tenant_id: str = Form(...)) -> dict:
    raise HTTPException(status_code=501, detail="FASE 2 — QuickBooks integration not yet active.")
