from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from services.runtime_config import apply_runtime_overrides


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="services/docling_service/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "docling-service"
    environment: str = "development"
    pdf_ocr_engine: str = "easyocr"
    easyocr_french_languages: str = "fr,en"
    easyocr_arabic_languages: str = "ar,en"
    easyocr_download_enabled: bool = True
    easyocr_model_storage_directory: str | None = None
    easyocr_use_gpu: bool | None = None
    docling_layout_model: str = "docling_layout_v2"
    docling_artifacts_path: str | None = None
    postgres_service_url: str = "http://127.0.0.1:8003"
    storage_service_url: str = "http://127.0.0.1:8012"

    @field_validator("easyocr_model_storage_directory", "docling_artifacts_path", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("easyocr_use_gpu", mode="before")
    @classmethod
    def _empty_bool_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


@lru_cache
def _get_base_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return apply_runtime_overrides(_get_base_settings())
