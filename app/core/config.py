import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEFAULT_SECRET_KEY = "dev-secret-key-change-in-production-min-32-chars!!"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    postgres_user: str = "commander"
    postgres_password: str = "commander"
    postgres_db: str = "commander"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    cors_origins: list[str] = ["http://localhost:4200", "http://127.0.0.1:4200", "http://localhost:3000"]

    # JWT — H1: default rejected in production
    secret_key: str = _DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Google OAuth (login)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""

    # Google Sheets OAuth
    google_sheets_redirect_uri: str = ""

    # Encryption (Fernet key, base64 url-safe 32 bytes)
    encryption_key: str = ""

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_voice_from: str = ""

    # ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"

    # Public backend URL (must be reachable by Twilio)
    backend_url: str = "http://localhost:8000"

    # H3: Frontend URL for OAuth redirects
    frontend_url: str = "http://localhost:4200"

    @model_validator(mode="after")
    def _derive_defaults(self) -> "Settings":
        """Derive redirect URIs from backend_url when not explicitly set."""
        base = self.backend_url.rstrip("/")
        if not self.google_redirect_uri:
            self.google_redirect_uri = f"{base}/api/v1/auth/google/callback"
        if not self.google_sheets_redirect_uri:
            self.google_sheets_redirect_uri = f"{base}/api/v1/sheets/callback"
        return self

    @model_validator(mode="after")
    def _check_production_settings(self) -> "Settings":
        """H1: Reject insecure defaults in production. H2: Warn about missing env vars."""
        if self.app_env != "development":
            if self.secret_key == _DEFAULT_SECRET_KEY:
                raise ValueError(
                    "SECRET_KEY must be changed from the default value in production"
                )
            missing = []
            if not self.google_client_id:
                missing.append("GOOGLE_CLIENT_ID")
            if not self.google_client_secret:
                missing.append("GOOGLE_CLIENT_SECRET")
            if not self.encryption_key:
                missing.append("ENCRYPTION_KEY")
            if not self.twilio_account_sid:
                missing.append("TWILIO_ACCOUNT_SID")
            if not self.twilio_auth_token:
                missing.append("TWILIO_AUTH_TOKEN")
            if missing:
                raise ValueError(
                    f"Missing required env vars for production: {', '.join(missing)}"
                )
        return self

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
