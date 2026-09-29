from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from services.orchestration_service.config import get_settings
from services.runtime_config import build_runtime_forward_headers


def _normalize_base(url: str) -> str:
    return url.rstrip("/") + "/"


def _client(*, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    settings = get_settings()
    request_headers = build_runtime_forward_headers()
    if headers:
        request_headers.update(headers)
    return httpx.AsyncClient(
        timeout=settings.request_timeout_seconds,
        headers=request_headers,
    )


def _is_retryable_http_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {502, 503, 504}:
        return True
    return False


async def _with_retry(
    operation,
    *,
    max_attempts: int,
    sleep_seconds: float,
):
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts or not _is_retryable_http_error(exc):
                raise
            await asyncio.sleep(sleep_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry helper exited unexpectedly.")


async def _get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    async def _operation() -> Any:
        async with _client(headers=headers) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    return await _with_retry(_operation, max_attempts=3, sleep_seconds=3)


async def _post_json(
    url: str,
    *,
    json: dict[str, Any] | None = None,
    files: Any = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    async def _operation() -> Any:
        async with _client(headers=headers) as client:
            response = await client.post(url, json=json, files=files, params=params)
            response.raise_for_status()
            return response.json()

    return await _with_retry(_operation, max_attempts=3, sleep_seconds=3)


async def _delete_json(url: str, *, json: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
    async def _operation() -> Any:
        async with _client() as client:
            response = await client.request("DELETE", url, json=json, params=params)
            response.raise_for_status()
            return response.json() if response.content else {}

    return await _with_retry(_operation, max_attempts=3, sleep_seconds=3)


async def probe_service(base_url: str | None) -> dict[str, Any]:
    if not base_url:
        return {
            "configured": False,
            "reachable": False,
            "url": None,
            "payload": None,
            "error": None,
        }

    target = urljoin(_normalize_base(base_url), "health")
    try:
        payload = await _get_json(target)
        return {
            "configured": True,
            "reachable": True,
            "url": base_url,
            "payload": payload,
            "error": None,
        }
    except httpx.HTTPError as exc:
        return {
            "configured": True,
            "reachable": False,
            "url": base_url,
            "payload": None,
            "error": str(exc),
        }


async def fetch_service_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "orchestration": await probe_service(settings.orchestration_service_url),
        "storage": await probe_service(settings.storage_service_url),
        "postgres": await probe_service(settings.postgres_service_url),
        "upload": await probe_service(settings.upload_service_url),
        "docling": await probe_service(settings.docling_service_url),
        "vlm": await probe_service(settings.vlm_service_url),
        "lightrag": await probe_service(settings.lightrag_service_url),
    }


async def init_tables() -> Any:
    settings = get_settings()
    return await _post_json(urljoin(_normalize_base(settings.postgres_service_url), "db/init"))


async def upload_file(file_name: str, content: bytes, content_type: str | None, *, provider: str = "nextcloud") -> Any:
    return await upload_file_with_metadata(
        file_name=file_name,
        content=content,
        content_type=content_type,
        provider=provider,
        metadata_json=None,
    )


async def upload_file_with_metadata(
    file_name: str,
    content: bytes,
    content_type: str | None,
    *,
    provider: str = "nextcloud",
    metadata_json: dict[str, str] | None = None,
) -> Any:
    settings = get_settings()
    files: dict[str, Any] = {"file": (file_name, content, content_type or "application/octet-stream")}
    if metadata_json:
        import json

        files["metadata_json"] = (None, json.dumps(metadata_json), "application/json")
    return await _post_json(
        urljoin(_normalize_base(settings.upload_service_url), "documents/upload"),
        files=files,
        params={"provider": provider},
    )


async def upload_base64_file(payload: dict[str, Any], *, provider: str = "nextcloud") -> Any:
    settings = get_settings()
    return await _post_json(
        urljoin(_normalize_base(settings.upload_service_url), "documents/upload"),
        json=payload,
        params={"provider": provider},
    )


async def run_docling(file_path: str, language_hint: str = "auto") -> Any:
    settings = get_settings()
    return await _post_json(
        urljoin(_normalize_base(settings.docling_service_url), "indexing/docling-only"),
        params={"file_path": file_path, "language_hint": language_hint},
    )


async def get_document_by_path(file_path: str) -> Any:
    settings = get_settings()
    return await _get_json(
        urljoin(_normalize_base(settings.postgres_service_url), "db/uploaded-documents/by-path"),
        params={"file_path": file_path},
    )


async def get_document_by_id(document_id: str) -> Any:
    settings = get_settings()
    return await _get_json(
        urljoin(_normalize_base(settings.postgres_service_url), f"db/uploaded-documents/{document_id}"),
    )


async def get_uploaded_document_metadata_options() -> Any:
    settings = get_settings()
    return await _get_json(
        urljoin(_normalize_base(settings.postgres_service_url), "db/uploaded-documents/metadata-options"),
    )


async def list_documents(limit: int | None = None) -> Any:
    settings = get_settings()
    params = {"limit": limit} if limit is not None else None
    return await _get_json(
        urljoin(_normalize_base(settings.postgres_service_url), "db/uploaded-documents"),
        params=params,
    )


async def get_latest_processing(document_id: str) -> Any:
    settings = get_settings()
    return await _get_json(
        urljoin(_normalize_base(settings.postgres_service_url), f"db/document-processing/latest/{document_id}"),
    )


async def get_latest_indexing_run(document_id: str) -> Any:
    settings = get_settings()
    return await _get_json(
        urljoin(_normalize_base(settings.postgres_service_url), f"db/indexing-runs/latest/by-document/{document_id}"),
    )


def choose_confidence(*, latest_processing: dict[str, Any] | None, docling_result: dict[str, Any] | None) -> tuple[str | None, float | None]:
    if latest_processing:
        value = latest_processing.get("ocr_confidence")
        if value is not None:
            try:
                return ("database.ocr_confidence", float(value))
            except (TypeError, ValueError):
                pass

    if docling_result:
        value = docling_result.get("easyocr_confidence")
        if value is not None:
            try:
                return ("docling.easyocr_confidence", float(value))
            except (TypeError, ValueError):
                pass

    return (None, None)


def should_use_vlm(*, document: dict[str, Any], confidence: float | None) -> bool:
    doc_type = (document.get("doc_type") or "").lower()
    if doc_type not in {"pdf", "jpg", "jpeg", "png", "tif", "tiff", "bmp", "webp"}:
        return False
    if confidence is None:
        return True
    return confidence < get_settings().confidence_threshold


async def trigger_vlm(processing_id: str, *, headers: dict[str, str] | None = None) -> Any:
    settings = get_settings()
    return await _post_json(
        urljoin(_normalize_base(settings.vlm_service_url), f"vlm/process-document/{processing_id}"),
        headers=headers,
    )


async def get_vlm_check(processing_id: str, *, headers: dict[str, str] | None = None) -> Any:
    settings = get_settings()
    return await _get_json(
        urljoin(_normalize_base(settings.vlm_service_url), f"vlm/process-check/{processing_id}"),
        headers=headers,
    )


async def wait_for_vlm(processing_id: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    settings = get_settings()
    deadline = time.monotonic() + settings.vlm_poll_timeout_seconds
    last_payload: dict[str, Any] | None = None

    while time.monotonic() < deadline:
        payload = await get_vlm_check(processing_id, headers=headers)
        last_payload = payload
        status = (payload.get("processing_status") or "").lower()
        if status in {"completed", "failed"}:
            return payload
        await asyncio.sleep(settings.vlm_poll_interval_seconds)

    return last_payload or {"processing_status": "timeout"}


async def run_lightrag_indexing(document_id: str) -> Any:
    settings = get_settings()
    return await _post_json(
        urljoin(_normalize_base(settings.lightrag_service_url), "indexing/text/full/by-document"),
        json={"document_id": document_id},
    )


async def run_lightrag_delete(document_id: str, *, delete_llm_cache: bool = False) -> Any:
    settings = get_settings()
    return await _post_json(
        urljoin(_normalize_base(settings.lightrag_service_url), "indexing/text/full/delete/by-document"),
        json={"document_id": document_id, "delete_llm_cache": delete_llm_cache},
    )


async def delete_storage_file(document_id: str) -> Any:
    settings = get_settings()
    return await _delete_json(
        urljoin(_normalize_base(settings.storage_service_url), "storage/delete"),
        params={"document_id": document_id},
    )


async def delete_uploaded_document(document_id: str) -> Any:
    settings = get_settings()
    return await _delete_json(
        urljoin(_normalize_base(settings.postgres_service_url), f"db/uploaded-documents/{document_id}"),
    )


async def purge_uploaded_document(document_id: str) -> Any:
    settings = get_settings()
    return await _delete_json(
        urljoin(_normalize_base(settings.postgres_service_url), f"db/uploaded-documents/{document_id}/purge"),
    )


async def run_lightrag_retrieval(
    *,
    query: str,
    top_k: int = 5,
    search_type: str = "hybrid",
    generate_answer: bool = True,
    evaluate_ragas: bool = False,
    answer: str | None = None,
    reference: str | None = None,
    filters: dict[str, list[str]] | None = None,
) -> Any:
    settings = get_settings()
    payload: dict[str, Any] = {
        "query": query,
        "top_k": top_k,
        "search_type": search_type,
        "generate_answer": generate_answer,
        "evaluate_ragas": evaluate_ragas,
    }
    if answer is not None:
        payload["answer"] = answer
    if reference is not None:
        payload["reference"] = reference
    if filters:
        payload["filters"] = filters

    return await _post_json(
        urljoin(_normalize_base(settings.lightrag_service_url), "retrieval/text"),
        json=payload,
    )
