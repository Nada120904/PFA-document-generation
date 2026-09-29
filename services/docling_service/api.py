"""Docling API endpoints."""

from __future__ import annotations

import time
import httpx
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from services.docling_service.config import get_settings
from services.docling_service.service import run_docling_only, supports_docling
from services.docling_service.utils.helpers import detect_supported_extension
from services.runtime_config import build_runtime_forward_headers
from services.storage_service.app.schemas import ProviderName

router = APIRouter(prefix="/indexing", tags=["docling"])

UPLOAD_REQUEST_RETRY_ATTEMPTS = 3
UPLOAD_REQUEST_RETRY_DELAY_SECONDS = 1.0


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
            time.sleep(UPLOAD_REQUEST_RETRY_DELAY_SECONDS)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Retry helper exited unexpectedly for {operation_name}.")

def save_uploaded_document(
    *,
    file_name: str,
    content_bytes: bytes,
    provider: ProviderName,
) -> dict:
    settings = get_settings()
    response = _with_retry(
        lambda: httpx.post(
            f"{settings.storage_service_url.rstrip('/')}/storage/upload",
            params={"provider": provider},
            files={
                "file": (
                    file_name,
                    content_bytes,
                    "application/octet-stream",
                )
            },
            timeout=120.0,
            headers=build_runtime_forward_headers(),
        ),
        operation_name="storage.upload",
    )
    response.raise_for_status()

    uploaded = response.json()
    file_type = detect_supported_extension(file_name)
    return {
        "document_id": uploaded["document_id"],
        "file_path": uploaded["file_path"],
        "file_type": file_type,
    }


@router.post("/docling-only")
def docling_only(file_path: str, language_hint: str = "auto") -> dict:
    try:
        return run_docling_only(file_path=file_path, language_hint=language_hint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "External service request failed."
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach an external service.") from exc


@router.post("/docling-only/upload")
async def docling_only_upload(
    file: UploadFile = File(...),
    provider: ProviderName = Query(..., description="Storage provider"),
    language_hint: str = Query("auto", description="OCR language hint: auto, french, or arabic"),
) -> dict:
    filename = file.filename or ""
    content = await file.read()
    try:
        uploaded = save_uploaded_document(
            file_name=filename,
            content_bytes=content,
            provider=provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "External service request failed."
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach an external service.") from exc

    if not supports_docling(uploaded["file_type"]):
        raise HTTPException(
            status_code=400,
            detail="This extraction mode supports only .txt, .pdf, .docx, and image files.",
        )

    return run_docling_only(
        file_path=uploaded["file_path"],
        document_id=uploaded["document_id"],
        language_hint=language_hint,
    )
