from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from services.runtime_config import apply_runtime_overrides


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Enterprise Storage Service"
    APP_ENV: str = "development"

    # Allow startup without env vars so request-scoped runtime headers can supply it.
    POSTGRES_SERVICE_URL: str = ""
    REQUEST_TIMEOUT_SECONDS: int = 60

    GRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"
    ONEDRIVE_CLIENT_ID: str | None = None
    ONEDRIVE_CLIENT_SECRET: str | None = None
    ONEDRIVE_AUTHORITY: str = "https://login.microsoftonline.com/common"
    ONEDRIVE_REFRESH_TOKEN: str | None = None
    ONEDRIVE_REFRESH_TOKEN_FILE: str = "refresh_token.txt"
    ONEDRIVE_ROOT_FOLDER: str = "HR-Documents"
    ONEDRIVE_UPLOAD_FOLDER: str = "raw-documents"
    ONEDRIVE_PROCESSED_FOLDER: str = "processed-documents"

    SHAREPOINT_POWER_AUTOMATE_URL: str = ""
    SHAREPOINT_FOLDER: str = "/sites/Document-AI-Project/Shared Documents/HR-Documents"
    SHAREPOINT_UPLOAD_FOLDER: str = "raw-documents"
    SHAREPOINT_PROCESSED_FOLDER: str = "processed-documents"

    NEXTCLOUD_BASE_URL: str | None = None
    NEXTCLOUD_USERNAME: str | None = None
    NEXTCLOUD_PASSWORD: str | None = None
    NEXTCLOUD_ROOT_PATH: str = "HR-Documents"
    NEXTCLOUD_UPLOAD_FOLDER: str = "raw-documents"
    NEXTCLOUD_PROCESSED_FOLDER: str = "processed-documents"

    STORAGE_URL: str | None = None
    STORAGE_USER: str | None = None
    STORAGE_PASSWORD: str | None = None
    STORAGE_VERIFY_TLS: bool = True
    STORAGE_PROVIDER: str = "nextcloud"

    POSTGRES_URL: str | None = None


@lru_cache
def _get_base_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return apply_runtime_overrides(_get_base_settings())


class _SettingsProxy:
    def __getattr__(self, name: str):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
