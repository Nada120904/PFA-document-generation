from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from services.runtime_config import apply_runtime_overrides


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="services/upload_service/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "upload-service"
    environment: str = "development"
    storage_service_url: str = "http://127.0.0.1:8012"
    storage_provider: str = "nextcloud"
    postgres_service_url: str = "http://127.0.0.1:8003"


@lru_cache
def _get_base_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return apply_runtime_overrides(_get_base_settings())
