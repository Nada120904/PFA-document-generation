from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

RUNTIME_ENV_KEYS: tuple[str, ...] = (
    "ENVIRONMENT",
    "LOG_LEVEL",
    "POSTGRES_URL",
    "POSTGRES_SERVICE_URL",
    "STORAGE_SERVICE_URL",
    "STORAGE_PROVIDER",
    "STORAGE_VERIFY_TLS",
    "STORAGE_URL",
    "STORAGE_USER",
    "STORAGE_PASSWORD",
    "NEXTCLOUD_BASE_URL",
    "NEXTCLOUD_USERNAME",
    "NEXTCLOUD_PASSWORD",
    "NEXTCLOUD_ROOT_PATH",
    "NEXTCLOUD_UPLOAD_FOLDER",
    "NEXTCLOUD_PROCESSED_FOLDER",
    "SHAREPOINT_POWER_AUTOMATE_URL",
    "SHAREPOINT_FOLDER",
    "SHAREPOINT_UPLOAD_FOLDER",
    "SHAREPOINT_PROCESSED_FOLDER",
    "ONEDRIVE_CLIENT_ID",
    "ONEDRIVE_CLIENT_SECRET",
    "ONEDRIVE_AUTHORITY",
    "ONEDRIVE_REFRESH_TOKEN",
    "ONEDRIVE_REFRESH_TOKEN_FILE",
    "ONEDRIVE_ROOT_FOLDER",
    "ONEDRIVE_UPLOAD_FOLDER",
    "ONEDRIVE_PROCESSED_FOLDER",
    "VLM_BASE_URL",
    "VLM_OCR_API_KEY",
    "VLM_MODEL_ID",
    "VLM_PROMPT",
    "VLM_PARSE_PROMPT",
    "VLM_REQUEST_TIMEOUT_SECONDS",
    "VLM_MAX_RETRIES",
    "VLM_RETRY_SLEEP_SECONDS",
    "VLM_UNLOAD_MODELS_ON_CUDA_ERROR",
)

_RUNTIME_OVERRIDES: ContextVar[dict[str, str]] = ContextVar("vlm_runtime_overrides", default={})
_SETTINGS_FIELD_BY_ENV_KEY: dict[str, str] = {
    "POSTGRES_SERVICE_URL": "postgres_service_url",
    "STORAGE_SERVICE_URL": "storage_service_url",
    "VLM_BASE_URL": "base_url",
    "VLM_OCR_API_KEY": "ocr_api_key",
    "VLM_MODEL_ID": "model_id",
    "VLM_PROMPT": "prompt",
    "VLM_PARSE_PROMPT": "parse_prompt",
    "VLM_REQUEST_TIMEOUT_SECONDS": "request_timeout_seconds",
    "VLM_MAX_RETRIES": "vlm_max_retries",
    "VLM_RETRY_SLEEP_SECONDS": "vlm_retry_sleep_seconds",
    "VLM_UNLOAD_MODELS_ON_CUDA_ERROR": "vlm_unload_models_on_cuda_error",
}


def _header_name(env_key: str) -> str:
    return f"x-rag-{env_key.lower().replace('_', '-')}"


def extract_runtime_overrides(headers: Any) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for env_key in RUNTIME_ENV_KEYS:
        value = headers.get(_header_name(env_key))
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            overrides[env_key] = cleaned
    return overrides


def get_runtime_overrides() -> dict[str, str]:
    return dict(_RUNTIME_OVERRIDES.get())


def build_runtime_forward_headers() -> dict[str, str]:
    overrides = get_runtime_overrides()
    return {_header_name(env_key): value for env_key, value in overrides.items()}


def apply_runtime_overrides(settings: Any) -> Any:
    overrides = get_runtime_overrides()
    if not overrides:
        return settings

    model_cls = type(settings)
    model_fields = getattr(model_cls, "model_fields", {})
    updates: dict[str, str] = {}
    for env_key, value in overrides.items():
        field_name = _SETTINGS_FIELD_BY_ENV_KEY.get(env_key, env_key.lower())
        if field_name in model_fields:
            updates[field_name] = value

    if not updates:
        return settings

    coerced_updates: dict[str, Any] = {}
    for field_name, value in updates.items():
        current_value = getattr(settings, field_name, None)

        if isinstance(current_value, bool):
            coerced_updates[field_name] = str(value).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        elif isinstance(current_value, int) and not isinstance(current_value, bool):
            coerced_updates[field_name] = int(str(value).strip())
        elif isinstance(current_value, float):
            coerced_updates[field_name] = float(str(value).strip())
        else:
            coerced_updates[field_name] = value

    return settings.model_copy(update=coerced_updates)


@contextmanager
def use_runtime_overrides(overrides: dict[str, str] | None):
    token = _RUNTIME_OVERRIDES.set(dict(overrides or {}))
    try:
        yield
    finally:
        _RUNTIME_OVERRIDES.reset(token)


async def bind_runtime_config(request: Any, call_next):
    token = _RUNTIME_OVERRIDES.set(extract_runtime_overrides(request.headers))
    try:
        return await call_next(request)
    finally:
        _RUNTIME_OVERRIDES.reset(token)
