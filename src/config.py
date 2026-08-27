"""Centralised application settings — local/free extraction by default."""
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

    # local = pdfplumber + reglas CoA ($0). cloud = OpenAI/LlamaParse/Groq (pago/límites).
    extraction_mode: str = Field(default="local")

    openai_api_key: SecretStr = Field(default=SecretStr(""))
    groq_api_key: SecretStr = Field(default=SecretStr(""))
    llamaparse_api_key: SecretStr = Field(default=SecretStr(""))

    supabase_url: str = Field(...)
    supabase_service_role_key: SecretStr = Field(...)
    # Legacy HS256 signing secret (Dashboard → API → JWT Secret). Optional if JWKS works.
    supabase_jwt_secret: str | None = Field(default=None)
    database_url: str | None = Field(default=None)

    # When false (default): JWT/membership bypass for local demos. Set true on Render.
    auth_enabled: bool = Field(default=False)
    # First authenticated user on an empty workspace becomes owner.
    auth_bootstrap_first_owner: bool = Field(default=True)
    # Comma-separated origins; empty / "*" → allow all (CORS open for now).
    allowed_origins: str = Field(default="*")

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    default_currency: str = Field(default="USD")
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)

    @property
    def cors_origins(self) -> list[str]:
        raw = (self.allowed_origins or "*").strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    google_oauth_client_id: str | None = Field(default=None)
    google_oauth_client_secret: SecretStr = Field(default=SecretStr(""))
    google_oauth_refresh_token: SecretStr = Field(default=SecretStr(""))
    google_drive_token_path: str | None = Field(default=None)
    google_drive_default_folder_id: str = Field(
        default="1db-aXczr9hHkv207U5gjEDmUfitN8MmT"
    )

    @property
    def use_local_extraction(self) -> bool:
        return (self.extraction_mode or "local").strip().lower() in {
            "local",
            "free",
            "offline",
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
