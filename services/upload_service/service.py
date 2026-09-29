"""Upload service business logic."""

from __future__ import annotations

import io
import json
import mimetypes
import time
from pathlib import Path

import httpx

from services.upload_service.config import get_settings
from services.upload_service.logging import get_logger
from services.runtime_config import build_runtime_forward_headers
from services.upload_service.utils.hashing import generate_file_hash
from services.upload_service.utils.helpers import detect_supported_extension

logger = get_logger("rag_system.upload_service")

UPLOAD_REQUEST_RETRY_ATTEMPTS = 3
UPLOAD_REQUEST_RETRY_DELAY_SECONDS = 1.0


class PostgresServiceError(RuntimeError):
    pass


class StorageUploadError(RuntimeError):
    pass


class StorageDownloadError(RuntimeError):
    pass


def _is_retryable_http_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and 500 <= exc.response.status_code <= 599:
        return True
    return False


def _with_retry(operation, *, operation_name: str):
    last_error: Exception | None = None
    for attempt in range(1, UPLOAD_REQUEST_RETRY_ATTEMPTS + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= UPLOAD_REQUEST_RETRY_ATTEMPTS or not _is_retryable_http_error(exc):
                raise
            logger.warning(
                "upload_service retrying operation=%s attempt=%s/%s error=%s",
                operation_name,
                attempt,
                UPLOAD_REQUEST_RETRY_ATTEMPTS,
                exc,
            )
            time.sleep(UPLOAD_REQUEST_RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Retry helper exited unexpectedly for {operation_name}.")


def _guess_mime_type(file_name: str, extension: str) -> str | None:
    guessed, _ = mimetypes.guess_type(file_name)
    if guessed:
        return guessed
    if extension == ".txt":
        return "text/plain"
    if extension == ".pdf":
        return "application/pdf"
    if extension == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if extension == ".png":
        return "image/png"
    if extension in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if extension == ".bmp":
        return "image/bmp"
    if extension == ".webp":
        return "image/webp"
    if extension in {".tif", ".tiff"}:
        return "image/tiff"
    return None


def _storage_endpoint(path: str) -> str:
    settings = get_settings()
    return f"{settings.storage_service_url.rstrip('/')}{path}"


def _storage_provider(provider: str | None = None) -> str:
    if provider is not None:
        normalized = str(provider).strip().lower()
        if normalized:
            return normalized
    settings = get_settings()
    return str(settings.storage_provider or "nextcloud").strip().lower() or "nextcloud"


def _get_uploaded_document_by_hash(file_hash: str) -> dict | None:
    settings = get_settings()
    endpoint = f"{settings.postgres_service_url.rstrip('/')}/db/uploaded-documents/by-hash/{file_hash}"

    def _operation() -> httpx.Response:
        return httpx.get(
            endpoint,
            timeout=30.0,
            headers=build_runtime_forward_headers(),
        )

    try:
        response = _with_retry(_operation, operation_name="postgres.by_hash")
    except httpx.HTTPError as exc:
        raise PostgresServiceError(f"Could not reach Postgres service: {exc}") from exc
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _get_uploaded_document_by_path(file_path: str) -> dict | None:
    settings = get_settings()
    endpoint = f"{settings.postgres_service_url.rstrip('/')}/db/uploaded-documents/by-path"

    def _operation() -> httpx.Response:
        return httpx.get(
            endpoint,
            params={"file_path": file_path},
            timeout=30.0,
            headers=build_runtime_forward_headers(),
        )

    try:
        response = _with_retry(_operation, operation_name="postgres.by_path")
    except httpx.HTTPError as exc:
        raise PostgresServiceError(f"Could not reach Postgres service: {exc}") from exc
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def _upload_via_storage_service(
    *,
    file_name: str,
    content_bytes: bytes,
    content_type: str | None,
    provider: str | None = None,
    metadata_json: dict[str, str] | None = None,
) -> dict:
    files_payload: dict[str, tuple[str | None, object, str | None]] = {
        "file": (
            file_name,
            io.BytesIO(content_bytes),
            content_type or "application/octet-stream",
        )
    }
    if metadata_json:
        files_payload["metadata_json"] = (
            None,
            json.dumps(metadata_json),
            "application/json",
        )

    def _operation() -> httpx.Response:
        return httpx.post(
            _storage_endpoint("/storage/upload"),
            params={"provider": _storage_provider(provider)},
            files=files_payload,
            timeout=120.0,
            headers=build_runtime_forward_headers(),
        )

    try:
        response = _with_retry(_operation, operation_name="storage.upload")
    except httpx.HTTPError as exc:
        raise StorageUploadError(f"Storage service upload failed: {exc}") from exc
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or str(exc)
        raise StorageUploadError(detail) from exc
    return response.json()


def _download_via_storage_service(*, document_id: str) -> tuple[bytes, str, str | None]:
    def _operation() -> httpx.Response:
        return httpx.get(
            _storage_endpoint("/storage/download"),
            params={"document_id": document_id},
            timeout=120.0,
            headers=build_runtime_forward_headers(),
        )

    try:
        response = _with_retry(_operation, operation_name="storage.download")
    except httpx.HTTPError as exc:
        raise StorageDownloadError(f"Storage service download failed: {exc}") from exc
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or str(exc)
        raise StorageDownloadError(detail) from exc

    content_type = response.headers.get("content-type")
    content_disposition = response.headers.get("content-disposition", "")
    file_name = "file"
    if "filename=" in content_disposition:
        file_name = content_disposition.split("filename=", 1)[1].strip().strip('"')

    return response.content, file_name, content_type


def save_uploaded_document(
    *,
    file_name: str,
    content_bytes: bytes,
    provider: str | None = None,
    metadata_json: dict[str, str] | None = None,
) -> dict:
    """Persist an uploaded file and create its DB row through the Postgres service."""

    extension = detect_supported_extension(file_name)
    if extension == ".txt":
        try:
            content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Uploaded .txt file must be UTF-8 encoded text.") from exc

    file_hash = generate_file_hash(content_bytes)
    existing_document = _get_uploaded_document_by_hash(file_hash)
    if existing_document is not None:
        existing_status = existing_document.get("status")
        if existing_status == "parsed":
            raise ValueError(
                f"This file already exists and is already parsed "
                f"(document_id={existing_document['document_id']})."
            )
        raise ValueError(
            f"This file already exists and is already uploaded "
            f"(document_id={existing_document['document_id']}, status={existing_status})."
        )

    document = _upload_via_storage_service(
        file_name=file_name,
        content_bytes=content_bytes,
        content_type=_guess_mime_type(file_name, extension),
        provider=provider,
        metadata_json=metadata_json,
    )
    logger.info(
        "Uploaded document %s through storage service to %s",
        document["document_id"],
        document["file_path"],
    )

    return {
        "document_id": document["document_id"],
        "file_path": document["file_path"],
        "file_name": document["file_name"],
        "file_type": extension,
        "metadata_json": document.get("metadata_json"),
        "status": document.get("status", "uploaded"),
    }


def read_remote_document_bytes(*, file_path: str) -> tuple[bytes, str, str]:
    document = _get_uploaded_document_by_path(file_path)
    if document is None:
        raise ValueError("No uploaded document record was found for this file path.")

    content_bytes, file_name, content_type = _download_via_storage_service(
        document_id=str(document["document_id"]),
    )
    extension = detect_supported_extension(file_name)

    return content_bytes, file_name, content_type or _guess_mime_type(file_name, extension)
