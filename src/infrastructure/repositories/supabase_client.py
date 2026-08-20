"""
Singleton Supabase client initialised from settings.
Import get_supabase_client() wherever you need DB access.
"""
from __future__ import annotations

from functools import lru_cache

from supabase import Client, create_client

from src.config import get_settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
    )
