from __future__ import annotations

from contextlib import contextmanager
import os
from contextvars import ContextVar
from typing import Any

RUNTIME_ENV_KEYS: tuple[str, ...] = (
    "ENVIRONMENT",
    "LOG_LEVEL",
    "POSTGRES_URL",
    "POSTGRES_SERVICE_URL",
    "DB_SERVICE_BASE_URL",
    "DB_SERVICE_TIMEOUT",
    "STORAGE_URL",
    "STORAGE_USER",
    "STORAGE_PASSWORD",
    "STORAGE_VERIFY_TLS",
    "STORAGE_PROVIDER",
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
    "GRAPH_BASE_URL",
    "ONEDRIVE_CLIENT_ID",
    "ONEDRIVE_CLIENT_SECRET",
    "ONEDRIVE_AUTHORITY",
    "ONEDRIVE_REFRESH_TOKEN",
    "ONEDRIVE_REFRESH_TOKEN_FILE",
    "ONEDRIVE_ROOT_FOLDER",
    "ONEDRIVE_UPLOAD_FOLDER",
    "ONEDRIVE_PROCESSED_FOLDER",
    "STORAGE_SERVICE_URL",
    "UPLOAD_SERVICE_URL",
    "DOCLING_SERVICE_URL",
    "VLM_SERVICE_URL",
    "LIGHTRAG_SERVICE_URL",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION",
    "QDRANT_INSECURE_TLS",
    "QDRANT_COLLECTION_ENTITIES",
    "QDRANT_COLLECTION_RELATIONSHIPS",
    "QDRANT_COLLECTION_CHUNKS",
    "QDRANT_VECTOR_NAME_ENTITIES",
    "QDRANT_VECTOR_NAME_RELATIONSHIPS",
    "QDRANT_VECTOR_NAME_CHUNKS",
    "NEO4J_URL",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_INSECURE_TLS",
    "CHATBOT_QUERY_OPTIMIZER_API_KEY",
    "CHATBOT_QUERY_OPTIMIZER_BASE_URL",
    "CHATBOT_QUERY_OPTIMIZER_MODEL",
    "CHATBOT_QUERY_OPTIMIZER_USE_LANGCHAIN",
    "CHATBOT_QUERY_OPTIMIZER_TIMEOUT_SECONDS",
    "CHATBOT_QUERY_OPTIMIZER_MAX_RETRIES",
    "CHATBOT_MEMORY_API_KEY",
    "CHATBOT_MEMORY_BASE_URL",
    "CHATBOT_MEMORY_MODEL",
    "CHATBOT_MEMORY_LLM_MODEL",
    "CHATBOT_MEMORY_EMBEDDING_MODEL",
    "CHATBOT_MEMORY_EMBEDDING_DIM",
    "CHATBOT_MEMORY_TOP_K",
    "CHATBOT_MEMORY_EXISTING_LIMIT",
    "CHATBOT_ANSWER_BASE_URL",
    "CHATBOT_ANSWER_MODEL",
    "CHATBOT_AUTH_SECRET",
    "CHATBOT_SUMMARY_MODEL",
    "CHATBOT_SUMMARY_TRIGGER_MESSAGES",
    "CHATBOT_SUMMARY_TRIGGER_TOKENS",
    "CHATBOT_SUMMARY_KEEP_MESSAGES",
    "CHATBOT_SUMMARY_TRIM_TOKENS",
    "CHATBOT_RETRIEVAL_ENABLED",
    "CHATBOT_RETRIEVAL_ORIGINAL_SUFFICIENT_SCORE",
    "CHATBOT_RETRIEVAL_SEARCH_TYPE",
    "CHATBOT_RETRIEVAL_TOP_K",
    "CHATBOT_RETRIEVAL_MAX_CHUNKS",
    "CHATBOT_RETRIEVAL_MAX_CHUNK_CHARS",
    "CHATBOT_RETRIEVAL_RERANK_TOP_N",
    "CHATBOT_RETRIEVAL_ENABLE_RERANKER",
    "CHATBOT_RETRIEVAL_MIN_RERANK_SCORE",
    "CHATBOT_RETRIEVAL_CONTEXT_TOP_N",
    "LLM_MODEL_NAME",
    "TIKTOKEN_MODEL_NAME",
    "OPENAI_EMBEDDING_MODEL",
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_DIM",
    "LLM_MODEL_MAX_ASYNC",
    "EMBEDDING_FUNC_MAX_ASYNC",
    "LLM_TIMEOUT",
    "EMBEDDING_TIMEOUT",
    "LIGHTRAG_WORKING_DIR",
    "LIGHTRAG_CHUNK_SIZE",
    "LIGHTRAG_CHUNK_OVERLAP_SIZE",
    "LIGHTRAG_ENABLE_HIERARCHICAL_INGESTION",
    "LIGHTRAG_HIERARCHICAL_SUMMARY_MAX_CHARS",
    "QDRANT_UPSERT_MAX_PAYLOAD_BYTES",
    "QDRANT_UPSERT_MAX_POINTS_PER_BATCH",
    "RERANK_BINDING",
    "RERANK_MODEL_NAME",
    "RERANK_BATCH_SIZE",
    "MIN_RERANK_SCORE",
    "RAGAS_LLM_MODEL_NAME",
    "RAGAS_EMBEDDING_MODEL_NAME",
    "FORCE_LLM_SUMMARY_ON_MERGE",
    "SUMMARY_MAX_TOKENS",
    "SUMMARY_CONTEXT_SIZE",
    "PDF_OCR_ENGINE",
    "EASYOCR_FRENCH_LANGUAGES",
    "EASYOCR_ARABIC_LANGUAGES",
    "EASYOCR_DOWNLOAD_ENABLED",
    "EASYOCR_MODEL_STORAGE_DIRECTORY",
    "EASYOCR_USE_GPU",
    "DOCLING_LAYOUT_MODEL",
    "VLM_BASE_URL",
    "VLM_OCR_API_KEY",
    "VLM_MODEL_ID",
    "VLM_PROMPT",
    "VLM_PARSE_PROMPT",
    "VLM_REQUEST_TIMEOUT_SECONDS",
    "VLM_MAX_RETRIES",
    "VLM_RETRY_SLEEP_SECONDS",
    "VLM_UNLOAD_MODELS_ON_CUDA_ERROR",
    "CONFIDENCE_THRESHOLD",
    "REQUEST_TIMEOUT_SECONDS",
    "VLM_POLL_INTERVAL_SECONDS",
    "VLM_POLL_TIMEOUT_SECONDS",
    "LIGHTRAG_TIMEOUT_SECONDS",
)

_RUNTIME_OVERRIDES: ContextVar[dict[str, str]] = ContextVar("runtime_overrides", default={})


def _header_name(env_key: str) -> str:
    return f"x-rag-{env_key.lower().replace('_', '-')}"


def extract_runtime_overrides(headers: Any) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for env_key in RUNTIME_ENV_KEYS:
        value = headers.get(_header_name(env_key))
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned == "":
            continue
        overrides[env_key] = cleaned
    return overrides


def get_runtime_overrides() -> dict[str, str]:
    return dict(_RUNTIME_OVERRIDES.get())


def get_runtime_env(env_key: str, default: str | None = None) -> str | None:
    overrides = get_runtime_overrides()
    if env_key in overrides:
        return overrides[env_key]
    return os.getenv(env_key, default)


def get_runtime_bool(env_key: str, default: bool = False) -> bool:
    value = get_runtime_env(env_key)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_runtime_int(env_key: str, default: int) -> int:
    value = get_runtime_env(env_key)
    if value is None or str(value).strip() == "":
        return default
    return int(str(value).strip())


def get_runtime_float(env_key: str, default: float) -> float:
    value = get_runtime_env(env_key)
    if value is None or str(value).strip() == "":
        return default
    return float(str(value).strip())


def build_runtime_forward_headers() -> dict[str, str]:
    overrides = get_runtime_overrides()
    return {_header_name(env_key): value for env_key, value in overrides.items()}


@contextmanager
def use_runtime_overrides(overrides: dict[str, str] | None):
    token = _RUNTIME_OVERRIDES.set(dict(overrides or {}))
    try:
        yield
    finally:
        _RUNTIME_OVERRIDES.reset(token)




def apply_runtime_overrides(settings: Any) -> Any:
    overrides = get_runtime_overrides()
    if not overrides:
        return settings

    model_cls = type(settings)
    model_fields = getattr(model_cls, "model_fields", {})
    updates: dict[str, str] = {}
    for env_key, value in overrides.items():
        field_name = env_key.lower()
        if field_name in model_fields:
            updates[field_name] = value
        elif env_key in model_fields:
            updates[env_key] = value

    if not updates:
        return settings
    return model_cls.model_validate({**settings.model_dump(), **updates})


async def bind_runtime_config(request: Any, call_next):
    token = _RUNTIME_OVERRIDES.set(extract_runtime_overrides(request.headers))
    try:
        return await call_next(request)
    finally:
        _RUNTIME_OVERRIDES.reset(token)
