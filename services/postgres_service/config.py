from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from services.runtime_config import apply_runtime_overrides


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="services/postgres_service/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "postgres-service"
    environment: str = "development"
    postgres_url: str = "postgresql+psycopg://username:password@host:5432/database_name"


@lru_cache
def _get_base_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return apply_runtime_overrides(_get_base_settings())
