"""Typed application settings, loaded once from the environment (12-factor).

Everything the platform needs is declared here, validated at startup so that a
misconfiguration fails fast instead of surfacing deep inside a running worker.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]

# Shipped default — fine for local dev, rejected in staging/production (see below).
INSECURE_DEFAULT_SECRET = "dev-only-change-me-secret-key-min-32-chars"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="EAP_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Enterprise Automation Platform"
    environment: Environment = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # --- security ---------------------------------------------------------
    secret_key: str = Field(default=INSECURE_DEFAULT_SECRET, min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_ttl: int = 900  # 15 minutes
    refresh_token_ttl: int = 60 * 60 * 24 * 7  # 7 days
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_per_minute: int = 120

    # --- persistence ------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./automation.db"
    redis_url: RedisDsn | None = None

    # --- automation runtime ----------------------------------------------
    # Plugins that touch the filesystem are confined to this sandbox root.
    workspace_dir: Path = Field(default=Path("./workspace"))
    default_step_timeout: float = 30.0
    default_step_retries: int = 2
    http_timeout_seconds: float = 15.0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _reject_default_secret_outside_dev(self) -> Settings:
        if self.environment in ("staging", "production") and (
            self.secret_key == INSECURE_DEFAULT_SECRET
        ):
            raise ValueError("EAP_SECRET_KEY must be set to a unique value outside development.")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def sqlalchemy_url(self) -> str:
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
