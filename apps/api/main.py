"""
LedgerAI FastAPI — REST API under /api + SPA static serve.
"""
from __future__ import annotations

import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config import get_settings
from src.container import get_container
from src.domain.exceptions import BookkeepingError
from src.domain.models.enums import (
    DocumentFileType,
    DocumentSource,
    DocumentStatus,
    TransactionStatus,
    TransactionType,
)
from src.domain.models.transaction import ExtractionMetadata, FinancialTransaction
from src.infrastructure.repositories.document_repository import DocumentRecord, DocumentRepository
from src.infrastructure.repositories.workspace_repository import Workspace, WorkspaceRepository
from src.use_cases.close_fiscal_year import FiscalYearAlreadyClosedError
from src.use_cases.close_period import PeriodAlreadyClosedError

_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "ledgerai_uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    key = settings.supabase_service_role_key.get_secret_value()
    if key.startswith("PENDIENTE") or len(key) < 20:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY missing. Set the service_role/secret key in .env"
        )
    from src.infrastructure.queue.document_worker import get_document_worker

    worker = get_document_worker()
    await worker.start_polling(interval_sec=8.0)
    yield
    await worker.stop_polling()


app = FastAPI(
    title="LedgerAI",
    version="0.5.0",
    description="Bookkeeping Clean-up Agent — professional API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


def _status_map(status: str | None) -> str | None:
    if not status or status == "all":
        return None
    if status == "pending":
        return TransactionStatus.PENDING_REVIEW.value
    return status


def _file_type(filename: str) -> DocumentFileType:
    ext = Path(filename).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return DocumentFileType.IMAGE
    if ext == ".pdf":
        return DocumentFileType.PDF
    if ext == ".csv":
        return DocumentFileType.CSV
    if ext in {".mp3", ".wav", ".m4a", ".ogg", ".webm"}:
        return DocumentFileType.AUDIO
    return DocumentFileType.OTHER


def _tx_json(tx: FinancialTransaction) -> dict:
    d = tx.model_dump(mode="json")
    return {
        **d,
        "date": d.get("transaction_date"),
        "account_code": d.get("chart_of_accounts_code"),
        "account_name": d.get("chart_of_accounts_name"),
        "category": d.get("chart_of_accounts_name"),
        "vendor": d.get("vendor_name"),
        "workspace_id": d.get("tenant_id"),
        "type": d.get("transaction_type"),
    }


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    from src.infrastructure.queue.document_worker import get_document_worker

    try:
        queue = await get_document_worker().queue_stats()
    except Exception:
        queue = {}
    return {
        "status": "ok",
        "version": "0.5.0",
        "product": "LedgerAI",
        "llm": "local_rules",
        "queue": queue,
        "extraction_mode": get_settings().extraction_mode,
    }


# ── Workspaces ────────────────────────────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str
    legal_name: str | None = None
    currency: str = "USD"
    fiscal_year_start: str = "01-01"
    industry: str | None = None
    timezone: str = "UTC"
    description: str | None = None


@api.get("/workspaces")
async def list_workspaces() -> list[dict]:
    rows = await WorkspaceRepository().list_all()
    return [r.model_dump(mode="json") for r in rows]


@api.post("/workspaces")
async def create_workspace(body: WorkspaceCreate) -> dict:
    ws = Workspace(
        name=body.name,
        legal_name=body.legal_name or body.description,
        currency=body.currency.upper(),
        fiscal_year_start=body.fiscal_year_start,
        industry=body.industry,
        timezone=body.timezone,
    )
    saved = await WorkspaceRepository().save(ws)
    # Auto-seed free CoA so classification works immediately
    try:
        await seed_chart_of_accounts(SeedCoABody(workspace_id=str(saved.id)))
    except Exception:
        pass
    return saved.model_dump(mode="json")


@api.get("/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str) -> dict:
    ws = await WorkspaceRepository().get(uuid.UUID(workspace_id))
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return ws.model_dump(mode="json")


@api.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str) -> dict:
    """Delete a workspace and its documents / txs / movements / CoA."""
    wid = uuid.UUID(workspace_id)
    repo = WorkspaceRepository()
    existing = await repo.get(wid)
    if not existing:
        raise HTTPException(404, "Workspace not found")
    await repo.delete(wid)
    return {"deleted": True, "id": workspace_id, "name": existing.name}


@api.get("/workspaces/{workspace_id}/stats")
async def workspace_stats(workspace_id: str) -> dict:
    tid = uuid.UUID(workspace_id)
    c = get_container()
    docs = DocumentRepository()
    txns = await c.transactions.list_by_tenant(tid, limit=5000)
    movements = await c.movements.list_by_tenant(tid, limit=5000)
    ledgers = await c.ledgers.list_by_tenant(tid, limit=120)
    all_docs = await docs.list_by_workspace(tid, limit=500)

    pending = sum(1 for t in txns if t.status == TransactionStatus.PENDING_REVIEW)
    verified = sum(1 for t in txns if t.status == TransactionStatus.VERIFIED)
    rejected = sum(1 for t in txns if t.status == TransactionStatus.REJECTED)
    unmatched = sum(1 for m in movements if m.status == TransactionStatus.PENDING_REVIEW)
    open_periods = sum(1 for l in ledgers if l.status == "open")
    income = sum((t.amount for t in txns if t.status == TransactionStatus.VERIFIED and t.transaction_type.value == "income"), Decimal("0"))
    expenses = sum((t.amount for t in txns if t.status == TransactionStatus.VERIFIED and t.transaction_type.value == "expense"), Decimal("0"))
    processing = sum(1 for d in all_docs if d.status == DocumentStatus.PROCESSING)

    return {
        "documents": len(all_docs),
        "processingDocs": processing,
        "pending_transactions": pending,
        "pendingReview": pending,
        "verified_transactions": verified,
        "verifiedTransactions": verified,
        "rejected_transactions": rejected,
        "unmatched_movements": unmatched,
        "periods_open": open_periods,
        "openPeriods": open_periods,
        "totalIncome": float(income),
        "totalExpenses": float(expenses),
        "netIncome": float(income - expenses),
    }


# ── Documents ─────────────────────────────────────────────────────────────────

def _folder_group_from_path(path: str | None, file_name: str | None = None) -> str:
    if not path:
        return "Subida local"
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if file_name and parts and parts[-1] == file_name:
        parts = parts[:-1]
    return " / ".join(parts) if parts else "Raíz Drive"


@api.get("/documents")
async def list_documents(workspace_id: str | None = None, tenant_id: str | None = None) -> list[dict]:
    wid = workspace_id or tenant_id
    if not wid:
        raise HTTPException(400, "workspace_id required")
    rows = await DocumentRepository().list_by_workspace(uuid.UUID(wid), limit=500)
    out = []
    for r in rows:
        folder = r.folder_group or _folder_group_from_path(r.drive_path, r.file_name)
        out.append(
            {
                **r.model_dump(mode="json"),
                "filename": r.file_name,
                "name": r.file_name,
                "folder_group": folder,
                "pipeline_kind": r.pipeline_kind or ("upload" if r.source == "upload" else "pending"),
                "apis_used": r.apis_used,
                "extract_preview": (r.raw_extracted_text or "")[:1200] or None,
            }
        )
    return out


@api.post("/documents/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    workspace_id: str = Form(...),
    tenant_id: str | None = Form(default=None),
) -> dict:
    """Enqueue upload for sequential processing (Render Free — 1 file at a time)."""
    from src.infrastructure.queue.document_worker import get_document_worker

    wid = uuid.UUID(workspace_id or tenant_id or "")
    filename = file.filename or "upload.bin"
    content = await file.read()
    ftype = _file_type(filename)
    worker = get_document_worker()

    kind = "spreadsheet" if ftype == DocumentFileType.CSV else "invoice"

    doc = await worker.enqueue_file(
        workspace_id=wid,
        filename=filename,
        content=content,
        file_type=ftype,
        source="upload",
        pipeline_kind=kind,
        apis_used="pdfplumber (local $0), reglas CoA"
        if ftype == DocumentFileType.PDF
        else ("csv-upload" if ftype == DocumentFileType.CSV else "local"),
        queue_payload={"plan_kind": kind},
        raw_note="En cola — procesamiento secuencial (1 archivo).",
    )
    background_tasks.add_task(worker.drain)

    return {
        **doc.model_dump(mode="json"),
        "filename": doc.file_name,
        "name": doc.file_name,
        "queued": True,
        "message": "Archivo en cola. Se procesa de a uno para no saturar Render Free.",
    }


@api.get("/queue/status")
async def queue_status() -> dict:
    from src.infrastructure.queue.document_worker import get_document_worker

    stats = await get_document_worker().queue_stats()
    return {"status": "ok", "queue": stats, "mode": "sequential_one_at_a_time"}


# ── Transactions ──────────────────────────────────────────────────────────────

@api.get("/transactions")
async def list_transactions(
    tenant_id: str,
    status: str | None = None,
    suspense: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> list[dict]:
    from src.infrastructure.classification.rule_coa import SUSPENSE_CODE

    tid = uuid.UUID(tenant_id)
    c = get_container()
    mapped = _status_map(status)
    if mapped == TransactionStatus.PENDING_REVIEW.value and not suspense:
        items = await c.transactions.list_pending(tid)
    else:
        items = await c.transactions.list_by_tenant(tid, limit=max(limit + offset, 5000), offset=0)
        if mapped:
            items = [t for t in items if t.status.value == mapped]
    if suspense:
        items = [
            t
            for t in items
            if (t.chart_of_accounts_code or t.ai_suggested_account_code or "") == SUSPENSE_CODE
            or (t.category_confidence is not None and float(t.category_confidence) < 0.4)
        ]
    page = items[offset : offset + limit]
    return [_tx_json(t) for t in page]


@api.get("/transactions/counts")
async def transaction_counts(tenant_id: str) -> dict:
    from src.infrastructure.classification.rule_coa import SUSPENSE_CODE

    tid = uuid.UUID(tenant_id)
    items = await get_container().transactions.list_by_tenant(tid, limit=5000)
    suspense_n = sum(
        1
        for t in items
        if (t.chart_of_accounts_code or t.ai_suggested_account_code or "") == SUSPENSE_CODE
        or (t.category_confidence is not None and float(t.category_confidence) < 0.4)
    )
    return {
        "all": len(items),
        "pending": sum(1 for t in items if t.status == TransactionStatus.PENDING_REVIEW),
        "pending_review": sum(1 for t in items if t.status == TransactionStatus.PENDING_REVIEW),
        "verified": sum(1 for t in items if t.status == TransactionStatus.VERIFIED),
        "rejected": sum(1 for t in items if t.status == TransactionStatus.REJECTED),
        "closed": sum(1 for t in items if t.status == TransactionStatus.CLOSED),
        "suspense": suspense_n,
    }


class ApproveBody(BaseModel):
    account_code: str | None = None
    account_name: str | None = None
    notes: str | None = None


class RejectBody(BaseModel):
    reason: str | None = None
    notes: str | None = None


class ReclassifyBody(BaseModel):
    account_code: str
    account_name: str
    type: str | None = None
    notes: str | None = None


class BulkBody(BaseModel):
    ids: list[str]
    reason: str | None = None


@api.post("/transactions/{transaction_id}/approve")
async def approve_transaction(transaction_id: str, body: ApproveBody = ApproveBody()) -> dict:
    from src.infrastructure.classification.rule_coa import SUSPENSE_NAME

    c = get_container()
    tx = await c.transactions.get_by_id(uuid.UUID(transaction_id))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    code = body.account_code or tx.ai_suggested_account_code or tx.chart_of_accounts_code or "9999"
    name = body.account_name or tx.ai_suggested_account_name or tx.chart_of_accounts_name or SUSPENSE_NAME
    saved = await c.transactions.save(tx.mark_verified(code, name, tx.category_confidence or 1.0))
    if body.notes:
        saved = await c.transactions.save(saved.model_copy(update={"notes": body.notes}))
    # Passive learning when user (or approval) pins a real account
    if body.account_code and body.account_code != "9999":
        c.coa.learn_from_correction(
            saved.tenant_id,
            saved.description or "",
            body.account_code,
            body.account_name or name,
        )
    return _tx_json(saved)


@api.post("/transactions/{transaction_id}/reject")
async def reject_transaction(transaction_id: str, body: RejectBody = RejectBody()) -> dict:
    c = get_container()
    tx = await c.transactions.get_by_id(uuid.UUID(transaction_id))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    notes = body.notes or body.reason
    saved = await c.transactions.save(tx.mark_rejected(notes))
    return _tx_json(saved)


@api.post("/transactions/{transaction_id}/reclassify")
async def reclassify_transaction(transaction_id: str, body: ReclassifyBody) -> dict:
    c = get_container()
    tx = await c.transactions.get_by_id(uuid.UUID(transaction_id))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    updates: dict = {
        "chart_of_accounts_code": body.account_code,
        "chart_of_accounts_name": body.account_name,
        "notes": body.notes,
        "status": TransactionStatus.VERIFIED,
        "category_confidence": 1.0,
    }
    if body.type:
        updates["transaction_type"] = body.type
    saved = await c.transactions.save(tx.model_copy(update=updates))
    learned = c.coa.learn_from_correction(
        saved.tenant_id,
        saved.description or "",
        body.account_code,
        body.account_name,
    )
    out = _tx_json(saved)
    if learned:
        out["learned_rule"] = learned
    return out


@api.post("/transactions/bulk-approve")
async def bulk_approve(body: BulkBody) -> dict:
    c = get_container()
    updated = 0
    for tid in body.ids:
        tx = await c.transactions.get_by_id(uuid.UUID(tid))
        if not tx or tx.status != TransactionStatus.PENDING_REVIEW:
            continue
        code = tx.ai_suggested_account_code or tx.chart_of_accounts_code
        name = tx.ai_suggested_account_name or tx.chart_of_accounts_name
        if not code or not name:
            continue
        await c.transactions.save(tx.mark_verified(code, name, tx.category_confidence or 0.8))
        updated += 1
    return {"updated": updated, "approved": updated}


@api.post("/transactions/bulk-reject")
async def bulk_reject(body: BulkBody) -> dict:
    c = get_container()
    updated = 0
    for tid in body.ids:
        tx = await c.transactions.get_by_id(uuid.UUID(tid))
        if not tx:
            continue
        await c.transactions.save(tx.mark_rejected(body.reason))
        updated += 1
    return {"updated": updated, "rejected": updated}


# Legacy PATCH for compatibility
class TransactionPatch(BaseModel):
    chart_of_accounts_code: str | None = None
    chart_of_accounts_name: str | None = None
    description: str | None = None
    verify: bool = False


@api.patch("/transactions/{transaction_id}")
async def patch_transaction(transaction_id: str, body: TransactionPatch, tenant_id: str) -> dict:
    c = get_container()
    tid = uuid.UUID(tenant_id)
    tx = await c.transactions.get_by_id(uuid.UUID(transaction_id))
    if not tx or tx.tenant_id != tid:
        raise HTTPException(404, "Transaction not found")
    updates: dict = {}
    if body.chart_of_accounts_code is not None:
        updates["chart_of_accounts_code"] = body.chart_of_accounts_code
    if body.chart_of_accounts_name is not None:
        updates["chart_of_accounts_name"] = body.chart_of_accounts_name
    if body.description is not None:
        updates["description"] = body.description
    if updates:
        tx = tx.model_copy(update=updates)
    if body.verify and tx.chart_of_accounts_code:
        tx = tx.mark_verified(
            tx.chart_of_accounts_code,
            tx.chart_of_accounts_name or "",
            tx.category_confidence or 1.0,
        )
    saved = await c.transactions.save(tx)
    return {"data": _tx_json(saved)}


# ── Chart of Accounts ─────────────────────────────────────────────────────────

@api.get("/chart-of-accounts")
async def chart_of_accounts(workspace_id: str) -> list[dict]:
    from src.infrastructure.repositories.supabase_client import get_supabase_client

    client = get_supabase_client()
    result = (
        client.table("chart_of_accounts")
        .select("id,code,name,account_type,description,subcategory,is_active")
        .eq("tenant_id", workspace_id)
        .order("code")
        .execute()
    )
    return [
        {
            **row,
            "category": row.get("account_type"),
            "workspace_id": workspace_id,
        }
        for row in result.data
    ]


class SeedCoABody(BaseModel):
    workspace_id: str


@api.post("/chart-of-accounts/seed")
async def seed_chart_of_accounts(body: SeedCoABody) -> dict:
    """Seed default LedgerAI CoA without paid embeddings ($0 / local stack)."""
    from apps.cli.seed_coa import DEFAULT_ACCOUNTS
    from src.infrastructure.repositories.supabase_client import get_supabase_client

    tid = body.workspace_id
    client = get_supabase_client()
    seeded = 0
    errors: list[str] = []
    for code, name, account_type, subcategory in DEFAULT_ACCOUNTS:
        row = {
            "tenant_id": tid,
            "code": code,
            "name": name,
            "account_type": account_type,
            "description": subcategory,
            "subcategory": subcategory,
            "is_active": True,
        }
        try:
            client.table("chart_of_accounts").upsert(
                row, on_conflict="tenant_id,code"
            ).execute()
            seeded += 1
        except Exception as exc:
            errors.append(f"{code}: {exc}")
    if seeded == 0 and errors:
        raise HTTPException(500, f"CoA seed failed: {errors[0]}")
    from src.infrastructure.classification.rule_coa import RuleCoAClassifier

    rules = RuleCoAClassifier().ensure_seed_rules(uuid.UUID(tid))
    return {
        "workspace_id": body.workspace_id,
        "seeded": seeded,
        "rules_seeded": len(rules),
        "embeddings": False,
        "engine": "local_rules",
        "errors": errors[:5],
    }


class AccountRuleCreate(BaseModel):
    workspace_id: str
    keywords: list[str]
    account_code: str
    account_name: str


@api.get("/account-rules")
async def list_account_rules(workspace_id: str) -> list[dict]:
    from src.infrastructure.classification.rule_coa import RuleCoAClassifier

    return RuleCoAClassifier().list_rules(uuid.UUID(workspace_id))


@api.post("/account-rules/seed")
async def seed_account_rules(body: SeedCoABody) -> dict:
    from src.infrastructure.classification.rule_coa import RuleCoAClassifier

    rows = RuleCoAClassifier().ensure_seed_rules(uuid.UUID(body.workspace_id))
    return {"workspace_id": body.workspace_id, "rules": len(rows), "engine": "local_rules"}


@api.post("/account-rules")
async def create_account_rule(body: AccountRuleCreate) -> dict:
    from src.infrastructure.repositories.supabase_client import get_supabase_client

    kws = [k.strip().lower() for k in body.keywords if k and k.strip()]
    if not kws:
        raise HTTPException(400, "keywords required")
    client = get_supabase_client()
    result = (
        client.table("account_rules")
        .insert(
            {
                "tenant_id": body.workspace_id,
                "keywords": kws,
                "account_code": body.account_code,
                "account_name": body.account_name,
                "source": "manual",
                "is_active": True,
            }
        )
        .execute()
    )
    get_container().coa.invalidate(uuid.UUID(body.workspace_id))
    return (result.data or [{}])[0]


# ── Movements / Reconciliation ────────────────────────────────────────────────

@api.get("/movements")
async def list_movements(
    workspace_id: str | None = None,
    tenant_id: str | None = None,
    statement_month: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict]:
    wid = workspace_id or tenant_id
    if not wid:
        raise HTTPException(400, "workspace_id required")
    c = get_container()
    tid = uuid.UUID(wid)
    if statement_month:
        movements = await c.movements.list_by_period(tid, statement_month)
    else:
        movements = await c.movements.list_by_tenant(tid, limit=limit)
    if status:
        movements = [m for m in movements if m.status.value == status]
    return [
        {
            **m.model_dump(mode="json"),
            "date": str(m.movement_date),
            "amount": float(abs(m.net_amount)),
            "matched": m.matched_transaction_id is not None,
            "transaction_id": str(m.matched_transaction_id) if m.matched_transaction_id else None,
        }
        for m in movements
    ]


class MatchBody(BaseModel):
    transaction_id: str


@api.post("/movements/{movement_id}/match")
async def match_movement(movement_id: str, body: MatchBody) -> dict:
    c = get_container()
    mov = await c.movements.get_by_id(uuid.UUID(movement_id))
    if not mov:
        raise HTTPException(404, "Movement not found")
    tx = await c.transactions.get_by_id(uuid.UUID(body.transaction_id))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    saved_mov = await c.movements.save(mov.mark_reconciled(transaction_id=tx.id))
    await c.transactions.save(
        tx.model_copy(update={"reconciled": True, "bank_movement_id": mov.id})
    )
    return {
        **saved_mov.model_dump(mode="json"),
        "matched": True,
        "transaction_id": body.transaction_id,
    }


@api.post("/movements/{movement_id}/unmatch")
async def unmatch_movement(movement_id: str) -> dict:
    c = get_container()
    mov = await c.movements.get_by_id(uuid.UUID(movement_id))
    if not mov:
        raise HTTPException(404, "Movement not found")
    if mov.matched_transaction_id:
        tx = await c.transactions.get_by_id(mov.matched_transaction_id)
        if tx:
            await c.transactions.save(
                tx.model_copy(update={"reconciled": False, "bank_movement_id": None})
            )
    saved = await c.movements.save(
        mov.model_copy(
            update={
                "matched_transaction_id": None,
                "status": TransactionStatus.PENDING_REVIEW,
            }
        )
    )
    return {**saved.model_dump(mode="json"), "matched": False, "transaction_id": None}


@api.post("/statements")
async def process_statement(
    file: UploadFile = File(...),
    tenant_id: str | None = Form(default=None),
    workspace_id: str | None = Form(default=None),
    bank_name: str = Form(default="Bank"),
    bank_account_number: str = Form(default="0000"),
    statement_month: str | None = Form(default=None),
) -> dict:
    wid = workspace_id or tenant_id
    if not wid:
        raise HTTPException(400, "workspace_id required")
    tid = uuid.UUID(wid)
    month = statement_month or date.today().strftime("%Y-%m")
    with NamedTemporaryFile(delete=False, suffix=".pdf", dir=_UPLOAD_DIR) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        report = await get_container().process_statement.execute(
            tmp_path, tid, bank_name, bank_account_number, month
        )
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    return {
        "total_movements": report.total_movements,
        "categorised": report.categorised,
        "reconciled": report.reconciled,
        "unmatched": report.unmatched,
        "ambiguous": report.ambiguous,
    }


# ── Periods / Reports ─────────────────────────────────────────────────────────

@api.get("/periods")
async def list_periods(workspace_id: str | None = None, tenant_id: str | None = None) -> list[dict]:
    """List closed/open ledgers, plus suggested months from verified txs (so UI is never blank)."""
    wid = workspace_id or tenant_id
    if not wid:
        raise HTTPException(400, "workspace_id required")
    tid = uuid.UUID(wid)
    c = get_container()
    ledgers = await c.ledgers.list_by_tenant(tid, limit=120)
    by_period: dict[str, dict] = {}
    for l in ledgers:
        by_period[l.fiscal_period] = {
            "id": str(l.id),
            "period": l.fiscal_period,
            "fiscal_period": l.fiscal_period,
            "status": l.status,
            "transaction_count": l.transaction_count,
            "net_income": str(l.net_income),
            "closed_at": l.closed_at.isoformat() if l.closed_at else None,
            "source": "ledger",
        }

    txns = await c.transactions.list_by_tenant(tid, limit=20000)
    month_counts: dict[str, int] = {}
    for t in txns:
        if t.status not in (TransactionStatus.VERIFIED, TransactionStatus.CLOSED):
            continue
        month = str(t.transaction_date)[:7]
        if len(month) == 7:
            month_counts[month] = month_counts.get(month, 0) + 1

    for month, count in month_counts.items():
        if month in by_period:
            by_period[month]["verified_count"] = count
            continue
        by_period[month] = {
            "id": None,
            "period": month,
            "fiscal_period": month,
            "status": "suggested",
            "transaction_count": count,
            "verified_count": count,
            "net_income": None,
            "closed_at": None,
            "source": "verified_txs",
        }

    return sorted(by_period.values(), key=lambda x: x["period"], reverse=True)


class PeriodAction(BaseModel):
    workspace_id: str | None = None
    tenant_id: str | None = None


@api.post("/periods/{fiscal_period}/close")
async def close_period(fiscal_period: str, body: PeriodAction = PeriodAction()) -> dict:
    wid = body.workspace_id or body.tenant_id
    if not wid:
        raise HTTPException(400, "workspace_id required")
    try:
        ledger = await get_container().close_period.execute(uuid.UUID(wid), fiscal_period)
    except PeriodAlreadyClosedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except BookkeepingError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "period": ledger.fiscal_period,
        "fiscal_period": ledger.fiscal_period,
        "status": ledger.status,
        "transaction_count": ledger.transaction_count,
        "net_income": str(ledger.net_income),
    }


@api.post("/periods/{fiscal_period}/reopen")
async def reopen_period(fiscal_period: str, body: PeriodAction) -> dict:
    wid = body.workspace_id or body.tenant_id
    if not wid:
        raise HTTPException(400, "workspace_id required")
    c = get_container()
    ledger = await c.ledgers.get_by_period(uuid.UUID(wid), fiscal_period)
    if not ledger:
        raise HTTPException(404, "Period not found")
    reopened = ledger.model_copy(update={"status": "open", "closed_at": None})
    saved = await c.ledgers.save(reopened)
    return {"period": saved.fiscal_period, "status": saved.status}


class FiscalYearBody(BaseModel):
    workspace_id: str
    notes: str | None = None
    allow_suspense: bool = False
    currency: str = "USD"


@api.get("/fiscal-years")
async def list_fiscal_years(workspace_id: str) -> dict:
    from src.use_cases.close_fiscal_year import FiscalYearCloseRepository

    tid = uuid.UUID(workspace_id)
    rows = FiscalYearCloseRepository().list_all(tid)
    return {"workspace_id": workspace_id, "years": rows}


@api.post("/fiscal-years/{fiscal_year}/close")
async def close_fiscal_year(fiscal_year: str, body: FiscalYearBody) -> dict:
    """Cierre anual: utilidad neta del año → Retained Earnings (3020)."""
    try:
        result = await get_container().close_fiscal_year.execute(
            uuid.UUID(body.workspace_id),
            fiscal_year,
            currency=body.currency,
            notes=body.notes,
            allow_suspense=body.allow_suspense,
        )
    except FiscalYearAlreadyClosedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except BookkeepingError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "fiscal_year": result.fiscal_year,
        "status": result.status,
        "total_revenue": result.total_revenue,
        "total_expenses": result.total_expenses,
        "net_income": result.net_income,
        "equity_draws_net": result.equity_draws_net,
        "transaction_count": result.transaction_count,
        "prior_retained_earnings": result.prior_retained_earnings,
        "retained_earnings_after": result.retained_earnings_after,
        "note": (
            "P&L del año queda histórico; el neto se acumula en utilidades retenidas "
            "para balances de años siguientes."
        ),
    }


@api.post("/fiscal-years/{fiscal_year}/reopen")
async def reopen_fiscal_year(fiscal_year: str, body: FiscalYearBody) -> dict:
    try:
        row = await get_container().close_fiscal_year.reopen(
            uuid.UUID(body.workspace_id), fiscal_year
        )
    except BookkeepingError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"fiscal_year": fiscal_year, "status": row.get("status"), "row": row}


@api.get("/reports/pnl")
async def pnl_report(
    workspace_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """P&L from verified txs — excludes Owner's Draws / equity (same engine as statements)."""
    from src.use_cases.emit_period_reports import EmitPeriodReportsUseCase

    bundle = await EmitPeriodReportsUseCase().execute(
        uuid.UUID(workspace_id),
        date_from=date_from,
        date_to=date_to,
    )
    pnl = dict(bundle.pnl)
    net = float(pnl.get("netIncome") or pnl.get("net_income") or 0)
    rev = float(pnl.get("totalRevenue") or pnl.get("revenue") or 0)
    revenue_items = pnl.get("revenueItems") or []
    expense_items = pnl.get("expenseItems") or []
    pnl.update(
        {
            "grossMargin": (net / rev * 100) if rev else 0,
            "lines": [
                *[
                    {"account": i["name"], "amount": i["amount"], "category": "revenue"}
                    for i in revenue_items
                ],
                *[
                    {"account": i["name"], "amount": i["amount"], "category": "expense"}
                    for i in expense_items
                ],
            ],
            "transactionCount": bundle.transaction_count,
        }
    )
    return pnl


@api.get("/reports/statements")
async def financial_statements_report(
    workspace_id: str,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Emit P&L + Balance + Cash flow for a month (YYYY-MM), year (YYYY), or date range."""
    from src.infrastructure.reconciliation.statement_chain import StatementPeriodRepository
    from src.use_cases.emit_period_reports import EmitPeriodReportsUseCase

    bundle = await EmitPeriodReportsUseCase().execute(
        uuid.UUID(workspace_id),
        period=period,
        date_from=date_from,
        date_to=date_to,
    )
    chain_alerts = StatementPeriodRepository().list_alerts(uuid.UUID(workspace_id))
    return {
        "workspace_id": bundle.workspace_id,
        "period_label": bundle.period_label,
        "date_from": bundle.date_from,
        "date_to": bundle.date_to,
        "currency": bundle.currency,
        "transaction_count": bundle.transaction_count,
        "engine": bundle.engine,
        "pnl": bundle.pnl,
        "balance_sheet": bundle.balance_sheet,
        "cash_flow": bundle.cash_flow,
        "cash_flow_monthly": bundle.cash_flow_monthly,
        "cash_flow_annual": bundle.cash_flow_annual,
        "balance_chain_alerts": chain_alerts,
    }


@api.get("/reports/balance-chain")
async def balance_chain_report(workspace_id: str) -> dict:
    """Cadenazo: periodos de extracto + alertas (apertura ≠ cierre mes anterior)."""
    from src.infrastructure.reconciliation.statement_chain import StatementPeriodRepository

    tid = uuid.UUID(workspace_id)
    repo = StatementPeriodRepository()
    periods = repo.list_by_tenant(tid)
    alerts = [p for p in periods if p.get("chain_ok") is False or p.get("paused")]
    return {
        "workspace_id": workspace_id,
        "periods": periods,
        "alerts": alerts,
        "alert_count": len(alerts),
    }


class ChainAckBody(BaseModel):
    workspace_id: str
    statement_month: str
    bank_account_number: str


@api.post("/reports/balance-chain/ack")
async def balance_chain_ack(body: ChainAckBody) -> dict:
    """Marca un cadenazo roto como revisado (quita pause)."""
    from src.infrastructure.reconciliation.statement_chain import acknowledge_chain

    row = acknowledge_chain(
        uuid.UUID(body.workspace_id),
        body.statement_month,
        body.bank_account_number,
    )
    return {"ok": True, "period": row}


# Legacy ingest endpoint
@api.post("/ingest")
async def ingest_legacy(
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
) -> dict:
    return await upload_document(file=file, workspace_id=tenant_id, tenant_id=tenant_id)


# ── Google Drive ──────────────────────────────────────────────────────────────

class DriveLinkBody(BaseModel):
    workspace_id: str
    folder_id: str
    folder_name: str | None = None


class DriveSyncBody(BaseModel):
    workspace_id: str
    folder_id: str | None = None
    max_files: int = 30
    ingest: bool = True


class DrivePushBody(BaseModel):
    workspace_id: str
    drive_file_id: str
    file_name: str
    drive_path: str
    content_base64: str
    mime_type: str | None = None


class DriveImportFilesBody(BaseModel):
    workspace_id: str
    files: list[dict]  # {id, name, path?, mime_type?}
    ingest: bool = True


@api.get("/drive/status")
async def drive_status() -> dict:
    from src.use_cases.sync_drive import SyncDriveUseCase

    return SyncDriveUseCase().status()


@api.post("/drive/link")
async def drive_link(body: DriveLinkBody) -> dict:
    from src.use_cases.sync_drive import SyncDriveUseCase

    return await SyncDriveUseCase().link_workspace(
        uuid.UUID(body.workspace_id), body.folder_id, body.folder_name
    )


@api.get("/drive/browse")
async def drive_browse(folder_id: str | None = None, depth: int = 1) -> dict:
    from src.infrastructure.drive.google_drive_client import DriveNotConfiguredError
    from src.use_cases.sync_drive import SyncDriveUseCase

    fid = folder_id or get_settings().google_drive_default_folder_id
    try:
        return await SyncDriveUseCase().browse(fid, depth=max(1, min(depth, 4)))
    except DriveNotConfiguredError as exc:
        raise HTTPException(503, str(exc)) from exc


@api.get("/drive/children")
async def drive_children(folder_id: str, parent_path: str | None = None) -> list[dict]:
    """One-level listing so the UI can enter nested folders (Wells → 8398 → 2026)."""
    from src.infrastructure.drive.google_drive_client import (
        DriveNotConfiguredError,
        GoogleDriveClient,
        credentials_available,
    )

    if not credentials_available():
        raise HTTPException(503, "Drive OAuth not configured")
    try:
        parent = GoogleDriveClient().get_file(folder_id)
        prefix = parent_path or parent.name
        kids = GoogleDriveClient().list_children(folder_id)
        return [
            {
                "id": n.id,
                "name": n.name,
                "mime_type": n.mime_type,
                "path": f"{prefix}/{n.name}",
                "is_folder": n.is_folder,
                "size": n.size,
                "children": [] if n.is_folder else None,
            }
            for n in kids
        ]
    except DriveNotConfiguredError as exc:
        raise HTTPException(503, str(exc)) from exc


@api.post("/drive/sync")
async def drive_sync(body: DriveSyncBody) -> dict:
    from src.infrastructure.drive.google_drive_client import DriveNotConfiguredError
    from src.use_cases.sync_drive import SyncDriveUseCase

    try:
        return await SyncDriveUseCase().sync(
            uuid.UUID(body.workspace_id),
            folder_id=body.folder_id,
            max_files=min(body.max_files, 100),
            ingest=body.ingest,
        )
    except DriveNotConfiguredError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


class DriveImportFolderBody(BaseModel):
    workspace_id: str
    folder_id: str
    max_files: int = 40
    ingest: bool = True


@api.post("/drive/import-folder")
async def drive_import_folder(body: DriveImportFolderBody, background_tasks: BackgroundTasks) -> dict:
    """Recursively collect PDFs/Excel under a Drive folder and queue import."""
    from src.infrastructure.drive.google_drive_client import GoogleDriveClient, credentials_available

    if not credentials_available():
        raise HTTPException(503, "Drive OAuth not configured")
    drive = GoogleDriveClient()
    root = drive.get_file(body.folder_id)
    files = []
    for node in drive.walk_ingestible(body.folder_id, prefix=root.name, max_files=min(body.max_files, 80)):
        files.append(
            {
                "id": node.id,
                "name": node.name,
                "path": node.path,
                "mime_type": node.mime_type,
            }
        )
    return await drive_import_files(
        DriveImportFilesBody(workspace_id=body.workspace_id, files=files, ingest=body.ingest),
        background_tasks,
    )


@api.post("/drive/import-files")
async def drive_import_files(body: DriveImportFilesBody, background_tasks: BackgroundTasks) -> dict:
    """Download selected Drive files, enqueue as pending, process 1-at-a-time."""
    from src.infrastructure.drive.classify import classify_drive_file
    from src.infrastructure.drive.google_drive_client import GoogleDriveClient, credentials_available
    from src.infrastructure.queue.document_worker import get_document_worker
    from src.use_cases.sync_drive import _file_type

    if not credentials_available():
        raise HTTPException(503, "Drive OAuth not configured")
    if not body.files:
        raise HTTPException(400, "No files selected")

    wid = uuid.UUID(body.workspace_id)
    docs = DocumentRepository()
    existing = await docs.list_by_workspace(wid, limit=5000)
    known = {d.drive_file_id for d in existing if d.drive_file_id}
    drive = GoogleDriveClient()
    worker = get_document_worker()

    imported = 0
    skipped = 0
    failed: list[dict] = []
    queued: list[dict] = []
    plans: list[dict] = []

    for item in body.files[:80]:
        fid = str(item.get("id") or "")
        name = str(item.get("name") or fid)
        path = str(item.get("path") or name)
        mime = str(item.get("mime_type") or "application/octet-stream")
        if not fid:
            continue
        if fid in known:
            skipped += 1
            continue
        plan = classify_drive_file(name, path, mime)
        plans.append({"file": name, "path": path, "kind": plan.kind, "note": plan.note})
        if plan.kind == "skip":
            skipped += 1
            continue
        try:
            content = drive.download_bytes(fid)
            ftype = _file_type(name, mime)
            folder = _folder_group_from_path(path, name)
            if plan.kind == "statement":
                apis = "pdfplumber (local $0), reglas CoA"
            elif plan.kind == "spreadsheet":
                apis = "Google Drive"
            else:
                apis = "pdfplumber (local $0), reglas CoA"

            doc = await worker.enqueue_file(
                workspace_id=wid,
                filename=name,
                content=content,
                file_type=ftype,
                source="google_drive",
                drive_file_id=fid,
                drive_path=path,
                pipeline_kind=plan.kind,
                apis_used=apis,
                folder_group=folder,
                vendor=plan.bank_name if plan.kind == "statement" else None,
                document_date=(
                    f"{plan.statement_month}-01"
                    if plan.kind == "statement"
                    and plan.statement_month
                    and len(plan.statement_month) == 7
                    else None
                ),
                queue_payload={
                    "plan_kind": plan.kind,
                    "bank_name": plan.bank_name,
                    "bank_account_number": plan.bank_account_number,
                    "statement_month": plan.statement_month,
                },
                raw_note=plan.note or "En cola — 1 archivo a la vez.",
            )
            imported += 1
            known.add(fid)
            queued.append(
                {
                    "id": str(doc.id),
                    "file_name": name,
                    "drive_path": path,
                    "status": doc.status.value,
                    "plan_kind": plan.kind,
                }
            )
        except Exception as exc:
            failed.append({"file": path, "error": str(exc)[:300]})

    if body.ingest and queued:
        background_tasks.add_task(worker.drain)

    statements = sum(1 for p in plans if p["kind"] == "statement")
    invoices = sum(1 for p in plans if p["kind"] == "invoice")
    sheets = sum(1 for p in plans if p["kind"] == "spreadsheet")

    return {
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "queued_for_ingest": len(queued) if body.ingest else 0,
        "classification": {"statements": statements, "invoices": invoices, "spreadsheets": sheets},
        "plans": plans[:40],
        "documents": [
            {"id": q["id"], "file_name": q["file_name"], "status": q["status"], "kind": q["plan_kind"]}
            for q in queued
        ],
        "message": (
            f"En cola {imported} "
            f"(estados {statements}, facturas {invoices}, excel {sheets}). "
            f"Procesamiento secuencial (1 a la vez) — no satura Render Free."
        ),
    }



@api.post("/drive/push-file")
async def drive_push_file(body: DrivePushBody) -> dict:
    """Ingest a Drive file payload (used when OAuth token is unavailable but files are pushed)."""
    import base64

    from src.container import get_container

    wid = uuid.UUID(body.workspace_id)
    docs = DocumentRepository()
    existing = await docs.list_by_workspace(wid, limit=2000)
    if any(d.drive_file_id == body.drive_file_id for d in existing):
        return {"status": "skipped", "reason": "already_imported", "drive_file_id": body.drive_file_id}

    content = base64.b64decode(body.content_base64)
    ftype = _file_type(body.file_name)
    doc = DocumentRecord(
        workspace_id=wid,
        file_name=body.file_name,
        file_type=ftype,
        file_size_bytes=len(content),
        status=DocumentStatus.PROCESSING,
        drive_file_id=body.drive_file_id,
        drive_path=body.drive_path,
        source="google_drive",
    )
    doc = await docs.save(doc)

    suffix = Path(body.file_name).suffix or ".bin"
    with NamedTemporaryFile(delete=False, suffix=suffix, dir=_UPLOAD_DIR) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        if ftype != DocumentFileType.CSV:
            result = await get_container().ingest.execute(tmp_path, wid)
            conf = 0.8
            vendor = None
            doc_date = None
            if not isinstance(result, list):
                conf = result.metadata.confidence_score
                vendor = result.vendor_name
                doc_date = str(result.transaction_date)
            doc = doc.model_copy(
                update={
                    "status": DocumentStatus.EXTRACTED,
                    "extraction_confidence": conf,
                    "vendor": vendor,
                    "document_date": doc_date,
                }
            )
        else:
            doc = doc.model_copy(update={"status": DocumentStatus.EXTRACTED})
        doc = await docs.save(doc)
    except Exception as exc:
        doc = doc.model_copy(update={"status": DocumentStatus.FAILED, "error_message": str(exc)[:500]})
        await docs.save(doc)
        raise HTTPException(422, str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "status": "imported",
        "document": {**doc.model_dump(mode="json"), "filename": doc.file_name},
    }


app.include_router(api)


# ── SPA static ────────────────────────────────────────────────────────────────

if _FRONTEND_DIST.exists():
    assets = _FRONTEND_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "health":
            raise HTTPException(404)
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = _FRONTEND_DIST / "index.html"
        if not index.exists():
            raise HTTPException(404, "Frontend not built. Run: cd frontend && npm run build")
        return FileResponse(index)
else:

    @app.get("/", include_in_schema=False)
    async def no_frontend():
        return {
            "message": "LedgerAI API running. Build frontend with: cd frontend && npm run build",
            "docs": "/docs",
            "health": "/health",
        }
