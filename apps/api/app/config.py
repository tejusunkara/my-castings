from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MY_CASTINGS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://my_castings:my_castings@localhost:5432/my_castings"

    # scrypt hash of the single login password; generate with `python -m app.services.auth`.
    # Empty means login is impossible, never that it's open.
    auth_password_hash: SecretStr = SecretStr("")
    jwt_secret: SecretStr = SecretStr("")
    session_ttl_hours: int = 24 * 7
    # Off only for local http://localhost development.
    cookie_secure: bool = True
    login_max_attempts: int = 5
    login_window_seconds: int = 15 * 60

    # Raw emails whose s3_bucket is "local" are read from this directory instead of S3
    # (local development and the seed script).
    raw_email_local_dir: Path = REPO_ROOT / "packages/ingestion_core/tests/fixtures"

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_strong_enough(cls, value: SecretStr) -> SecretStr:
        # HS256 keys under 32 bytes are brute-forceable. Empty = login disabled.
        secret = value.get_secret_value()
        if secret and len(secret.encode()) < 32:
            raise ValueError("jwt_secret must be at least 32 bytes (or empty to disable login)")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
