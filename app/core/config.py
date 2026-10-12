"""
Application configuration via pydantic-settings.

All settings are read from environment variables (or .env file).
See .env.example for the full list.
"""

from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──
    database_url: str = (
        "postgresql+psycopg://querypilot:querypilot_dev@localhost:5432/querypilot"
    )
    readonly_database_url: str = (
        "postgresql+psycopg://querypilot_ro:querypilot_ro_dev@localhost:5432/querypilot"
    )

    # ── LLM ──
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 30

    # ── Application mode ──
    mock_mode: bool = True

    # ── Safety and limits ──
    max_sql_retries: int = 2
    max_clarification_rounds: int = 3
    max_result_rows: int = 100
    sql_statement_timeout_ms: int = 5000

    # ── Logging ──
    log_level: str = "INFO"

    # ── Postgres container (used only by seed/migration scripts) ──
    postgres_user: str = "querypilot"
    postgres_password: str = "querypilot_dev"
    postgres_db: str = "querypilot"

    @property
    def sync_database_url(self) -> str:
        """Return a synchronous database URL (for Alembic)."""
        return self.database_url.replace("+psycopg", "+psycopg")

    @property
    def sync_readonly_database_url(self) -> str:
        """Return a synchronous read-only database URL."""
        return self.readonly_database_url.replace("+psycopg", "+psycopg")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
