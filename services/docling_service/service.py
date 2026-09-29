"""Docling service business logic."""

from __future__ import annotations

import datetime
import math
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from services.docling_service.config import get_settings
from services.docling_service.logging import get_logger
from services.docling_service.storage.storage_client import StorageServiceClient
from services.docling_service.utils.helpers import detect_supported_extension
from services.docling_service.utils.ids import generate_processing_id
from services.runtime_config import build_runtime_forward_headers

logger = get_logger("rag_system.docling_service")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
DOCLING_EXTENSIONS = {".txt", ".pdf", ".docx", *IMAGE_EXTENSIONS}
POSTGRES_UPDATE_RETRY_ATTEMPTS = 3
POSTGRES_UPDATE_RETRY_DELAY_SECONDS = 1.5
HTTP_REQUEST_RETRY_ATTEMPTS = 3
HTTP_REQUEST_RETRY_DELAY_SECONDS = 1.0


def _safe_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed):
        return None
    return parsed


def _postgres_endpoint(path: str) -> str:
    settings = get_settings()
    return f"{settings.postgres_service_url.rstrip('/')}{path}"


def _is_retryable_http_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError) and 500 <= exc.response.status_code <= 599:
        return True
    return False


def _with_retry(operation, *, operation_name: str):
    last_error: Exception | None = None
    for attempt in range(1, HTTP_REQUEST_RETRY_ATTEMPTS + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= HTTP_REQUEST_RETRY_ATTEMPTS or not _is_retryable_http_error(exc):
                raise
            logger.warning(
                "docling_service retrying operation=%s attempt=%s/%s error=%s",
                operation_name,
                attempt,
                HTTP_REQUEST_RETRY_ATTEMPTS,
                exc,
            )
            time.sleep(HTTP_REQUEST_RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Retry helper exited unexpectedly for {operation_name}.")


def _get_uploaded_document(*, file_path: str, document_id: str | None) -> dict:
    def _operation() -> httpx.Response:
        if document_id is not None:
            return httpx.get(
                _postgres_endpoint(f"/db/uploaded-documents/{document_id}"),
                timeout=30.0,
                headers=build_runtime_forward_headers(),
            )
        return httpx.get(
            _postgres_endpoint("/db/uploaded-documents/by-path"),
            params={"file_path": file_path},
            timeout=30.0,
            headers=build_runtime_forward_headers(),
        )

    response = _with_retry(
        _operation,
        operation_name="postgres.get_uploaded_document_by_id" if document_id is not None else "postgres.get_uploaded_document_by_path",
    )

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="No uploaded document record was found for this file. Upload the file first with the storage service.",
        )
    response.raise_for_status()
    return response.json()


def _update_uploaded_document(document_id: str, payload: dict) -> dict:
    response = _with_retry(
        lambda: httpx.patch(
            _postgres_endpoint(f"/db/uploaded-documents/{document_id}"),
            json=payload,
            timeout=30.0,
            headers=build_runtime_forward_headers(),
        ),
        operation_name="postgres.update_uploaded_document",
    )
    response.raise_for_status()
    return response.json()


def _update_uploaded_document_with_retry(
    document_id: str,
    payload: dict,
    *,
    suppress_final_error: bool = False,
) -> dict | None:
    last_error: Exception | None = None
    for attempt in range(1, POSTGRES_UPDATE_RETRY_ATTEMPTS + 1):
        try:
            return _update_uploaded_document(document_id, payload)
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code
            is_retryable = status_code >= 500
            if not is_retryable or attempt == POSTGRES_UPDATE_RETRY_ATTEMPTS:
                break
            logger.warning(
                "Retrying uploaded document update for %s after HTTP %s (attempt %s/%s)",
                document_id,
                status_code,
                attempt,
                POSTGRES_UPDATE_RETRY_ATTEMPTS,
            )
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == POSTGRES_UPDATE_RETRY_ATTEMPTS:
                break
            logger.warning(
                "Retrying uploaded document update for %s after transport error (attempt %s/%s): %s",
                document_id,
                attempt,
                POSTGRES_UPDATE_RETRY_ATTEMPTS,
                exc,
            )
        time.sleep(POSTGRES_UPDATE_RETRY_DELAY_SECONDS)

    if suppress_final_error:
        logger.warning(
            "Uploaded document update still failed after retries for %s payload=%s error=%s",
            document_id,
            payload,
            last_error,
        )
        return None

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Uploaded document update failed for {document_id}.")


def _create_document_processing(payload: dict) -> dict:
    response = _with_retry(
        lambda: httpx.post(
            _postgres_endpoint("/db/document-processing"),
            json=payload,
            timeout=30.0,
            headers=build_runtime_forward_headers(),
        ),
        operation_name="postgres.create_document_processing",
    )
    response.raise_for_status()
    return response.json()


def _update_document_processing(processing_id: str, payload: dict) -> dict:
    response = _with_retry(
        lambda: httpx.patch(
            _postgres_endpoint(f"/db/document-processing/{processing_id}"),
            json=payload,
            timeout=30.0,
            headers=build_runtime_forward_headers(),
        ),
        operation_name="postgres.update_document_processing",
    )
    response.raise_for_status()
    return response.json()


def build_convert_pipeline_options() -> Any:
    from docling.datamodel.pipeline_options import ConvertPipelineOptions

    pipeline_options = ConvertPipelineOptions()
    return pipeline_options


def build_document_processing_payload(*, document_id: str, processing_status: str) -> dict:
    return {
        "processing_id": generate_processing_id(),
        "document_id": document_id,
        "processing_status": processing_status,
        "parsed_at": None,
        "parser_name": None,
        "parser_version": None,
        "used_ocr": None,
        "ocr_engine": None,
        "ocr_confidence": None,
        "layout_confidence": None,
        "parse_confidence": None,
        "table_confidence": None,
        "mean_confidence": None,
        "low_confidence": None,
        "used_vlm": False,
        "vlm_model": None,
        "markdown_text": None,
        "vlm_started_at": None,
        "vlm_processing_time": None,
    }


def build_processing_results_payload(processed: dict, *, processing_status: str) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    confidence = processed.get("confidence") or {}
    docling_document = processed.get("docling_document") or {}

    return {
        "processing_status": processing_status,
        "parsed_at": now,
        "parser_name": "docling",
        "parser_version": docling_document.get("version"),
        "used_ocr": bool(processed.get("used_ocr")),
        "ocr_engine": processed.get("ocr_engine"),
        "ocr_confidence": _safe_float(confidence.get("ocr_score")),
        "layout_confidence": _safe_float(confidence.get("layout_score")),
        "parse_confidence": _safe_float(confidence.get("parse_score")),
        "table_confidence": _safe_float(confidence.get("table_score")),
        "mean_confidence": _safe_float(confidence.get("mean_score") or confidence.get("mean_grade")),
        "low_confidence": _safe_float(confidence.get("low_score") or confidence.get("low_grade")),
        "used_vlm": False,
        "vlm_model": None,
        "markdown_text": processed.get("content"),
        "vlm_started_at": None,
        "vlm_processing_time": None,
    }


def supports_docling(extension: str) -> bool:
    return extension in DOCLING_EXTENSIONS


def run_docling_processing(file_path: str, language_hint: str = "auto") -> dict:
    extension = detect_supported_extension(Path(file_path).name)
    logger.info("Detected file type %s for Docling processing on %s", extension, file_path)

    if extension == ".txt":
        from services.docling_service.ingestion.text.processor import process_text

        return process_text(file_path)
    if extension == ".pdf":
        from services.docling_service.ingestion.pdf.processor import process_pdf

        return process_pdf(file_path, language_hint=language_hint)
    if extension == ".docx":
        from services.docling_service.ingestion.docx.processor import process_docx

        return process_docx(file_path)
    if extension in IMAGE_EXTENSIONS:
        from services.docling_service.ingestion.image.processor import process_image

        return process_image(file_path, language_hint=language_hint)
    raise HTTPException(
        status_code=400,
        detail="Docling processing supports only .txt, .pdf, .docx, and image files.",
    )


def _download_remote_file(
    document_id: str,
    file_name: str | None = None,
) -> Path:
    client = StorageServiceClient()
    return client.download_to_tempfile(
        document_id=document_id,
        file_name=file_name,
    )


def run_docling_only(file_path: str, document_id: str | None = None, language_hint: str = "auto") -> dict:
    started_at = time.perf_counter()
    processing = None
    temp_file_path: Path | None = None

    document = _get_uploaded_document(file_path=file_path, document_id=document_id)
    document_id = document["document_id"]
    file_name = document.get("file_name") or Path(file_path).name
    extension = detect_supported_extension(file_name)
    if document.get("status") == "parsed":
        logger.info("Skipped Docling processing for %s because document %s is already parsed", file_path, document_id)
        return {
            "document_id": document_id,
            "processing_id": None,
            "file_path": file_path,
            "markdown_text": None,
            "docling_metadata": None,
            "docling_confidence": None,
            "easyocr_confidence": None,
            "ocr_engine": None,
            "docling_duration_seconds": 0.0,
            "status": "already_parsed",
            "message": "This file was already parsed.",
        }

    _update_uploaded_document_with_retry(document_id, {"doc_type": extension.lstrip("."), "status": "parsing"})
    processing = _create_document_processing(
        build_document_processing_payload(document_id=document_id, processing_status="parsing")
    )
    logger.info("Updated document %s status to parsing", document_id)

    try:
        temp_file_path = _download_remote_file(
            document_id=document_id,
            file_name=file_name,
        )
        processed = run_docling_processing(str(temp_file_path), language_hint=language_hint)
    except Exception as exc:
        _update_uploaded_document_with_retry(document_id, {"status": "error"}, suppress_final_error=True)
        if processing is not None:
            _update_document_processing(processing["processing_id"], {"processing_status": "error"})
        logger.exception("Docling-only preprocessing failed for %s", file_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if temp_file_path is not None and temp_file_path.exists():
            temp_file_path.unlink(missing_ok=True)
            logger.info("Deleted temporary Docling file %s", temp_file_path)

    docling_duration_seconds = round(time.perf_counter() - started_at, 3)

    processing = _update_document_processing(
        processing["processing_id"],
        build_processing_results_payload(processed, processing_status="parsed"),
    )
    _update_uploaded_document_with_retry(document_id, {"status": "parsed"}, suppress_final_error=True)
    logger.info("Updated document %s status to parsed", document_id)

    logger.info("Finished Docling-only processing for %s in %.3f sec", file_path, docling_duration_seconds)
    return {
        "document_id": document_id,
        "processing_id": processing["processing_id"],
        "file_path": file_path,
        "markdown_text": processed["content"],
        "docling_metadata": processed["docling_document"],
        "docling_confidence": processed.get("confidence"),
        "easyocr_confidence": processed.get("easyocr_confidence")
        or _safe_float((processed.get("confidence") or {}).get("ocr_score")),
        "ocr_engine": processed.get("ocr_engine"),
        "docling_duration_seconds": docling_duration_seconds,
        "status": processed.get("status"),
    }
