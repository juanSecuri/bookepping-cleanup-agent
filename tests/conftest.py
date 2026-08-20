"""
Pytest configuration shared across all tests.
"""
from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("LLAMAPARSE_API_KEY", "test-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:test@localhost:5432/postgres")


@pytest.fixture
def tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000001")
