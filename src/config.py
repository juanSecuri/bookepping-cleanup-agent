"""Centralised application settings — OpenAI-first (no Anthropic)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: SecretStr = Field(...)
    groq_api_key: SecretStr = Field(...)
    llamaparse_api_key: SecretStr = Field(...)

    supabase_url: str = Field(...)
    supabase_service_role_key: SecretStr = Field(...)
    database_url: str | None = Field(default=None)

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    default_currency: str = Field(default="USD")
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
