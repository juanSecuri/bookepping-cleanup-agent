"""
CLI — Bulk Historical Ingestion
================================
Recursively processes a folder of historical accounting documents and
ingests them all into the Bookkeeping Clean-up Agent pipeline.

Usage
─────
  python -m apps.cli.ingest \\
      --folder  /path/to/documents \\
      --tenant  <UUID> \\
      [--workers 4] \\
      [--dry-run]

Supported file types
────────────────────
  Images   : .jpg .jpeg .png .webp         → OpenAI vision extraction
  Audio    : .mp3 .wav .m4a .ogg           → Groq Whisper + OpenAI structuring
  PDF      : .pdf                           → LlamaParse + OpenAI
  Text     : .txt                           → OpenAI text structuring

The CLI reads BANK_STATEMENT_MONTHS from the folder structure.  If you
organise documents as  2023/01/  then the parent folder name is used as
the fiscal_period hint (YYYY-MM) when invoking ProcessStatementUseCase
for PDFs whose filenames contain "estado_cuenta", "bank_statement", or
"extracto".

Progress is written to  ingestion_report_<timestamp>.json  in the same
folder.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Make sure project root is on sys.path when running as a module
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.use_cases.ingest_document import IngestDocumentUseCase
from src.use_cases.process_statement import ProcessStatementUseCase

# ── constants ────────────────────────────────────────────────────────────────

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
PDF_SUFFIX = {".pdf"}
TEXT_SUFFIX = {".txt"}
ALL_SUPPORTED = IMAGE_SUFFIXES | AUDIO_SUFFIXES | PDF_SUFFIX | TEXT_SUFFIX

BANK_STATEMENT_PATTERNS = re.compile(
    r"(estado_cuenta|bank_statement|extracto|statement|estado de cuenta)",
    re.IGNORECASE,
)

FISCAL_PERIOD_FROM_PATH = re.compile(r"(\d{4})[/_\-]?(0[1-9]|1[0-2])")


# ── helpers ──────────────────────────────────────────────────────────────────

def _detect_fiscal_period(path: Path) -> str | None:
    """
    Infer YYYY-MM from the file path.
    Checks filename → parent folder → grandparent folder.
    """
    for part in [path.stem, path.parent.name, path.parent.parent.name]:
        m = FISCAL_PERIOD_FROM_PATH.search(part)
        if m:
            return f"{m.group(1)}-{m.group(2)}"
    return None


def _collect_files(folder: Path) -> list[Path]:
    """Recursively collect all supported files, sorted for reproducibility."""
    files = sorted(
        f for f in folder.rglob("*")
        if f.is_file() and f.suffix.lower() in ALL_SUPPORTED
    )
    return files


def _is_bank_statement(path: Path) -> bool:
    return bool(BANK_STATEMENT_PATTERNS.search(path.name))


# ── processing ───────────────────────────────────────────────────────────────

async def _process_file(
    path: Path,
    tenant_id: uuid.UUID,
    dry_run: bool,
) -> dict[str, Any]:
    """Process a single file and return a result dict for the report."""
    result: dict[str, Any] = {
        "file": str(path),
        "suffix": path.suffix.lower(),
        "status": "pending",
        "type": None,
        "detail": None,
        "error": None,
    }

    if dry_run:
        result["status"] = "dry_run"
        return result

    try:
        suffix = path.suffix.lower()

        if suffix in PDF_SUFFIX and _is_bank_statement(path):
            # Use ProcessStatementUseCase for bank statement PDFs
            fiscal_period = _detect_fiscal_period(path) or "2024-01"
            report = await ProcessStatementUseCase().execute(
                pdf_path=path,
                tenant_id=tenant_id,
                bank_name="Desconocido",
                bank_account_number="0000",
                statement_month=fiscal_period,
            )
            result["type"] = "bank_statement"
            result["status"] = "ok"
            result["detail"] = {
                "total_movements": report.total_movements,
                "categorised": report.categorised,
                "reconciled": report.reconciled,
                "unmatched": report.unmatched,
            }
        else:
            # Generic ingestion (image, audio, invoice PDF, text)
            output = await IngestDocumentUseCase().execute(path, tenant_id)
            if isinstance(output, list):
                result["type"] = "bank_movements"
                result["detail"] = {"count": len(output)}
            else:
                result["type"] = "transaction"
                result["detail"] = {
                    "id": str(output.id),
                    "description": output.description,
                    "amount": str(output.amount),
                    "chart_of_accounts_code": output.chart_of_accounts_code,
                    "status": output.status.value,
                }
            result["status"] = "ok"

    except Exception as exc:  # noqa: BLE001
        result["status"] = "error"
        result["error"] = str(exc)

    return result


async def _run(
    folder: Path,
    tenant_id: uuid.UUID,
    workers: int,
    dry_run: bool,
) -> None:
    files = _collect_files(folder)
    if not files:
        print(f"No supported files found under {folder}")
        return

    print(f"Found {len(files)} file(s) to process (workers={workers}, dry_run={dry_run})")

    semaphore = asyncio.Semaphore(workers)
    results: list[dict[str, Any]] = []
    completed = 0

    async def bounded(path: Path) -> dict[str, Any]:
        async with semaphore:
            return await _process_file(path, tenant_id, dry_run)

    tasks = [asyncio.create_task(bounded(f)) for f in files]

    for coro in asyncio.as_completed(tasks):
        result = await coro
        completed += 1
        status_icon = "✓" if result["status"] == "ok" else ("~" if result["status"] == "dry_run" else "✗")
        print(
            f"  [{completed:>4}/{len(files)}] {status_icon}  {Path(result['file']).name}"
            + (f"  — {result['error']}" if result["error"] else "")
        )
        results.append(result)

    # ── summary ──
    ok = sum(1 for r in results if r["status"] == "ok")
    errors = [r for r in results if r["status"] == "error"]
    print(f"\n{'─'*60}")
    print(f"  Processed : {len(files)}")
    print(f"  OK        : {ok}")
    print(f"  Errors    : {len(errors)}")

    # ── save report ──
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = folder / f"ingestion_report_{ts}.json"
    report_path.write_text(
        json.dumps(
            {
                "tenant_id": str(tenant_id),
                "folder": str(folder),
                "dry_run": dry_run,
                "started_at": ts,
                "total": len(files),
                "ok": ok,
                "errors": len(errors),
                "results": results,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"  Report    : {report_path}")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk-ingest historical accounting documents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--folder", "-f",
        required=True,
        type=Path,
        help="Root folder containing historical documents (searched recursively).",
    )
    parser.add_argument(
        "--tenant", "-t",
        required=True,
        type=uuid.UUID,
        help="Tenant UUID.",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=3,
        help="Number of concurrent AI calls (default: 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Discover files without sending them to the AI pipeline.",
    )

    args = parser.parse_args()

    if not args.folder.exists():
        parser.error(f"Folder does not exist: {args.folder}")
    if not args.folder.is_dir():
        parser.error(f"Path is not a directory: {args.folder}")

    asyncio.run(_run(args.folder, args.tenant, args.workers, args.dry_run))


if __name__ == "__main__":
    main()
