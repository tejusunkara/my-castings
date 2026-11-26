from functools import lru_cache
from pathlib import Path
from typing import Self
from urllib.parse import quote

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MY_CASTINGS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://my_castings:my_castings@localhost:5432/my_castings"
    # On AWS the database credentials arrive as separate values from the secret RDS
    # generates (ECS injects each JSON field); when db_host is set, database_url is
    # built from these instead.
    db_host: str | None = None
    db_port: int = 5432
    db_name: str | None = None
    db_user: str | None = None
    db_password: SecretStr | None = None

    # scrypt hash of the single login password; generate with `python -m app.services.auth`.
    # Empty means login is impossible, never that it's open.
    auth_password_hash: SecretStr = SecretStr("")
    jwt_secret: SecretStr = SecretStr("")
    session_ttl_hours: int = 24 * 7
    # Off only for local http://localhost development.
    cookie_secure: bool = True
    # Where the real client address comes from, for the login rate limiter. In production
    # "cloudfront-viewer-address": CloudFront sets it (clients can't), and only CloudFront
    # can reach the API. Unset: the connection's address (local development).
    client_ip_header: str | None = None
    login_max_attempts: int = 5
    login_window_seconds: int = 15 * 60

    # Media files (headshots, reels, ...). On AWS the bucket is real S3 and credentials come
    # from the task role; locally s3_endpoint_url points at the RustFS container from
    # docker-compose.yml, with its keys below.
    media_bucket: str = "my-castings-media"
    s3_region: str = "us-east-1"
    s3_endpoint_url: str | None = None
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    # Origins allowed to upload to and read from the media bucket (bucket CORS).
    media_cors_origins: list[str] = ["http://localhost:5173"]

    # Raw emails whose s3_bucket is "local" are read from this directory instead of S3
    # (local development and the seed script).
    raw_email_local_dir: Path = REPO_ROOT / "packages/ingestion_core/tests/fixtures"

    @model_validator(mode="after")
    def database_url_from_parts(self) -> Self:
        if self.db_host:
            if not (self.db_name and self.db_user and self.db_password):
                raise ValueError("db_host needs db_name, db_user and db_password too")
            password = quote(self.db_password.get_secret_value(), safe="")
            user = quote(self.db_user, safe="")
            self.database_url = (
                f"postgresql+psycopg://{user}:{password}@{self.db_host}:{self.db_port}"
                f"/{self.db_name}?sslmode=require"
            )
        return self

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
