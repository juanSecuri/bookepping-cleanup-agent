"""Unit tests for Supabase Storage document helpers (mocked)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.infrastructure.storage.document_storage import (
    object_key,
    resolve_document_bytes,
)


def test_object_key_format() -> None:
    wid, did = uuid4(), uuid4()
    assert object_key(wid, did, "stmt.pdf") == f"{wid}/{did}.pdf"


def test_resolve_document_bytes_local_first(tmp_path: Path) -> None:
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.4")
    data = resolve_document_bytes(local_path=str(f), storage_path="ws/id.pdf")
    assert data.startswith(b"%PDF")


def test_resolve_document_bytes_storage_fallback() -> None:
    with patch(
        "src.infrastructure.storage.document_storage.get_document_bytes",
        return_value=b"from-storage",
    ):
        data = resolve_document_bytes(local_path=None, storage_path="ws/id.pdf")
    assert data == b"from-storage"


def test_resolve_document_bytes_raises_when_missing() -> None:
    with pytest.raises(FileNotFoundError):
        resolve_document_bytes(local_path="/nope/missing.pdf", storage_path=None)


def test_put_document_bytes_calls_storage() -> None:
    from src.infrastructure.storage.document_storage import put_document_bytes

    mock_client = MagicMock()
    bucket = MagicMock()
    mock_client.storage.from_.return_value = bucket
    wid, did = uuid4(), uuid4()
    with patch(
        "src.infrastructure.storage.document_storage.get_supabase_client",
        return_value=mock_client,
    ):
        key = put_document_bytes(wid, did, "a.pdf", b"hello")
    assert key == f"{wid}/{did}.pdf"
    bucket.upload.assert_called_once()
