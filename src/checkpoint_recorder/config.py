from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str
    # Required in production (webhook mode); optional for local polling
    webhook_url: str | None = None
    webhook_secret: str | None = None

    # Database
    database_url: str           # asyncpg — runtime
    database_sync_url: str      # psycopg2 — Alembic only

    # Server
    port: int = 8080

    # NLP (SU-002)
    nlp_confidence_threshold: float = 0.65

    # Timeouts (SU-001, SU-009)
    parse_attempt_expiry_hours: int = 24
    periodicity_prompt_expiry_hours: int = 24

    # Cleanup (SU-006)
    deferred_cleanup_days: int = 30

    # Observability
    parse_attempt_dangling_detection_seconds: int = 30

    # Scheduler
    scheduler_interval_hours: int = 12

    # Set to true locally to skip webhook and use long-polling instead
    polling_mode: bool = False

    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def webhook_path(self) -> str:
        import hashlib
        token_hash = hashlib.sha256(self.telegram_bot_token.encode()).hexdigest()[:16]
        return f"/webhook/{token_hash}"

    @property
    def webhook_full_url(self) -> str:
        if not self.webhook_url:
            raise RuntimeError("WEBHOOK_URL is required in webhook mode")
        return self.webhook_url.rstrip("/") + self.webhook_path

    def require_webhook(self) -> None:
        """Call at startup in webhook mode to fail fast if config is incomplete."""
        if not self.webhook_url:
            raise RuntimeError("WEBHOOK_URL must be set in webhook mode")
        if not self.webhook_secret:
            raise RuntimeError("WEBHOOK_SECRET must be set in webhook mode")


settings = Settings()
