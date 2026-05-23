from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    reverb_token: str = Field(default="", alias="REVERB_TOKEN")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    database_url: str = Field(default="sqlite:///./guitar_searcher.db", alias="GS_DATABASE_URL")
    max_concurrency: int = Field(default=8, alias="GS_MAX_CONCURRENCY")
    per_host_rps: float = Field(default=2.0, alias="GS_PER_HOST_RPS")
    user_agent: str = Field(
        default="guitar-searcher/0.1 (+https://example.invalid)",
        alias="GS_USER_AGENT",
    )
    log_level: str = Field(default="INFO", alias="GS_LOG_LEVEL")

    notify_from: str = Field(default="", alias="GS_NOTIFY_FROM")
    notify_to: str = Field(default="", alias="GS_NOTIFY_TO")
    smtp_host: str = Field(default="", alias="GS_SMTP_HOST")
    smtp_port: int = Field(default=587, alias="GS_SMTP_PORT")
    smtp_username: str = Field(default="", alias="GS_SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="GS_SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="GS_SMTP_USE_TLS")

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])

    @property
    def seed_data_dir(self) -> Path:
        return Path(__file__).resolve().parent / "db" / "seed_data"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
