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
    database_url: str | None = Field(default=None)

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    default_currency: str = Field(default="USD")
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)

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
