from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from services.runtime_config import apply_runtime_overrides


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="services/orchestration_service/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "orchestration-service"
    environment: str = "development"
    postgres_service_url: str = "http://host.docker.internal:8008"
    upload_service_url: str = "http://host.docker.internal:8011"
    docling_service_url: str = "http://host.docker.internal:8005"
    vlm_service_url: str = "http://host.docker.internal:8003"
    lightrag_service_url: str = "http://host.docker.internal:8000"
    storage_service_url: str = "http://host.docker.internal:8012"
    orchestration_service_url: str = "http://host.docker.internal:8002"
    confidence_threshold: float = 0.95
    request_timeout_seconds: float = 900.0
    vlm_poll_interval_seconds: float = 2.0
    vlm_poll_timeout_seconds: float = 90.0

    @field_validator(
        "postgres_service_url",
        "upload_service_url",
        "docling_service_url",
        "vlm_service_url",
        "lightrag_service_url",
        "storage_service_url",
        "orchestration_service_url",
        mode="before",
    )
    @classmethod
    def _empty_url_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def _get_base_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return apply_runtime_overrides(_get_base_settings())
