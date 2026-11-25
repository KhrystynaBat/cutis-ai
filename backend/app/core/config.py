from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://dermalab:dermalab@127.0.0.1:55432/dermalab"
    secret_key: str = Field(default="change-me", min_length=8)

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:4200"]

    storage_dir: Path = Path("storage")
    models_dir: Path = Path("../models")
    max_upload_mb: int = 10
    upload_max_per_window: int = 30  # photo uploads per doctor within the window
    upload_window_seconds: int = 600
    max_concurrent_analyses: int = 1

    ai_enabled: bool = True
    max_queued_analyses: int = 10
    analysis_timeout_seconds: int = 300
    xai_overlay_max_side: int = 1024

    email_provider: Literal["log", "smtp"] = "log"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from: str = ""
    smtp_from_name: str = "CutisAI"
    smtp_starttls: bool = True  # port 465 uses implicit TLS instead
    smtp_timeout_seconds: int = 20
    patient_email_notifications: bool = True
    patient_email_attach_pdf: bool = True
    app_base_url: str = "http://localhost:8080"
    email_max_attempts: int = 5

    display_timezone: str = "Europe/Kyiv"

    session_ttl_hours: int = 8  # absolute lifetime
    session_idle_minutes: int = 60  # sliding inactivity timeout
    cookie_secure: bool = False
    login_max_failures: int = 5  # per IP + email within the window
    login_window_seconds: int = 900
    login_email_confirmation: bool = True
    login_link_ttl_minutes: int = 10
    login_resend_cooldown_seconds: int = 60
    login_letters_max: int = 5  # sign-in letters per user within the window
    login_letters_window_minutes: int = 15
    invitation_ttl_hours: int = 72
    password_reset_ttl_hours: int = 24
    email_change_ttl_hours: int = 24
    email_change_requests_max: int = 3
    email_change_window_minutes: int = 60

    admin_email: str = ""
    admin_password: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("secret_key")
    @classmethod
    def _no_default_secret_in_production(cls, v: str, info) -> str:
        if info.data.get("environment") == "production" and (v == "change-me" or len(v) < 32):
            raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters in production")
        return v

    @field_validator("cookie_secure")
    @classmethod
    def _secure_cookies_in_production(cls, v: bool, info) -> bool:
        if info.data.get("environment") == "production" and not v:
            raise ValueError("COOKIE_SECURE must be true in production (HTTPS only)")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
