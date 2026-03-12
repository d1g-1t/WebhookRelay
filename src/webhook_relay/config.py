from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "WebhookRelay"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/webhook_relay"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40

    REDIS_URL: str = "redis://redis:6379/0"

    DEFAULT_MAX_RETRIES: int = 5
    DEFAULT_RETRY_BACKOFF_BASE: float = 2.0
    DEFAULT_RETRY_MAX_DELAY_SECONDS: int = 3600
    DEFAULT_TIMEOUT_SECONDS: int = 30

    CB_FAILURE_THRESHOLD: int = 5
    CB_FAILURE_WINDOW_SECONDS: int = 60
    CB_RECOVERY_TIMEOUT_SECONDS: int = 300

    HMAC_TIMESTAMP_TOLERANCE_SECONDS: int = 300

    ARQ_MAX_JOBS: int = 50
    ARQ_JOB_TIMEOUT_SECONDS: int = 60
    RETRY_POLL_INTERVAL_SECONDS: int = 30


settings = Settings()
