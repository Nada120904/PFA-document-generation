from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.runtime_config import apply_runtime_overrides

SERVICE_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(SERVICE_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "vlm-service"
    environment: str = "development"

    postgres_service_url: str = Field(
        default="http://127.0.0.1:8000",
        validation_alias=AliasChoices("POSTGRES_SERVICE_URL"),
    )
    storage_service_url: str = Field(
        default="http://127.0.0.1:8001",
        validation_alias=AliasChoices("STORAGE_SERVICE_URL"),
    )
    base_url: str = Field(
        default="http://102.54.244.89:8088/ocr",
        validation_alias=AliasChoices("VLM_BASE_URL", "BASE_URL"),
    )
    ocr_api_key: str = Field(
        default="key",
        validation_alias=AliasChoices("VLM_OCR_API_KEY", "OCR_API_KEY"),
    )
    model_id: str = Field(
        default="Qwen/Qwen3-VL-2B-Instruct",
        validation_alias=AliasChoices("VLM_MODEL_ID", "MODEL_ID"),
    )
    prompt: str = Field(
        default="qwenvl markdown",
        validation_alias=AliasChoices("VLM_PROMPT", "PROMPT"),
    )
    request_timeout_seconds: int = Field(
        default=600,
        validation_alias=AliasChoices("VLM_REQUEST_TIMEOUT_SECONDS", "REQUEST_TIMEOUT_SECONDS"),
    )
    parse_prompt: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VLM_PARSE_PROMPT", "PARSE_PROMPT"),
    )
    vlm_max_retries: int = Field(
        default=3,
        validation_alias=AliasChoices("VLM_MAX_RETRIES"),
    )
    vlm_retry_sleep_seconds: int = Field(
        default=120,
        validation_alias=AliasChoices("VLM_RETRY_SLEEP_SECONDS"),
    )
    vlm_unload_models_on_cuda_error: bool = Field(
        default=True,
        validation_alias=AliasChoices("VLM_UNLOAD_MODELS_ON_CUDA_ERROR"),
    )


@lru_cache
def _get_base_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return apply_runtime_overrides(_get_base_settings())
