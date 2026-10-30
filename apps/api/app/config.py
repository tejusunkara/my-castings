from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MY_CASTINGS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://my_castings:my_castings@localhost:5432/my_castings"


@lru_cache
def get_settings() -> Settings:
    return Settings()
