"""
Pytest configuration shared across all tests.

Provides fixtures for:
  - A consistent tenant_id
  - A mock settings object (no .env required during CI)
"""
from __future__ import annotations

import os
import uuid

import pytest


# ── Prevent real API calls during unit tests ─────────────────────────────────
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("LLAMAPARSE_API_KEY", "test-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:test@localhost:5432/postgres")


@pytest.fixture
def tenant_id() -> uuid.UUID:
    """A consistent tenant UUID for use in tests."""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")
