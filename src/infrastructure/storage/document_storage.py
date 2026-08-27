"""Supabase Storage for document bytes — survives Render redeploys."""
from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from uuid import UUID

from src.infrastructure.repositories.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

DEFAULT_BUCKET = "documents"


def storage_bucket() -> str:
    return (os.environ.get("SUPABASE_STORAGE_BUCKET") or DEFAULT_BUCKET).strip()


def object_key(workspace_id: UUID, document_id: UUID, filename: str) -> str:
    suffix = Path(filename).suffix or ".bin"
    return f"{workspace_id}/{document_id}{suffix}"


def _content_type(filename: str) -> str:
    media, _ = mimetypes.guess_type(filename)
    return media or "application/octet-stream"


def put_document_bytes(
    workspace_id: UUID,
    document_id: UUID,
    filename: str,
    content: bytes,
) -> str:
    """Upload bytes; returns storage object key."""
    key = object_key(workspace_id, document_id, filename)
    bucket = storage_bucket()
    client = get_supabase_client()
    client.storage.from_(bucket).upload(
        key,
        content,
        file_options={"content-type": _content_type(filename), "upsert": "true"},
    )
    logger.info("Supabase Storage: %s bytes → %s/%s", len(content), bucket, key)
    return key


def get_document_bytes(storage_path: str) -> bytes:
    bucket = storage_bucket()
    client = get_supabase_client()
    data = client.storage.from_(bucket).download(storage_path)
    if isinstance(data, bytes):
        return data
    return bytes(data)


def materialize_to_path(storage_path: str, dest: Path) -> Path:
    """Download from Storage to a local Path (for pdfplumber/Tesseract pipelines)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(get_document_bytes(storage_path))
    return dest


def resolve_document_bytes(
    *,
    local_path: str | None,
    storage_path: str | None,
) -> bytes:
    """Read document bytes from local cache or Supabase Storage."""
    if local_path:
        path = Path(local_path)
        if path.exists():
            return path.read_bytes()
    if storage_path:
        return get_document_bytes(storage_path)
    raise FileNotFoundError("document bytes not on disk or in storage")
