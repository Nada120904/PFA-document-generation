"""Upload API endpoints."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
import httpx
from pydantic import ValidationError

from services.upload_service.base64_files import (
    Base64FilePayload,
    base64_payload_from_bytes,
    decode_base64_file,
)
from services.upload_service.service import (
    PostgresServiceError,
    StorageDownloadError,
    StorageUploadError,
    read_remote_document_bytes,
    save_uploaded_document,
)
from services.upload_service.utils.helpers import detect_supported_extension

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/ping")
def ping() -> dict:
    return {"message": "upload router is working"}


@router.post("/upload")
async def upload_document(
    request: Request,
    provider: str = Query(default="nextcloud"),
    file: UploadFile | None = File(default=None),
    metadata_json: str | None = Form(default=None),
) -> dict:
    """Upload a supported document to the server and track it through the Postgres service."""

    try:
        content_type = request.headers.get("content-type", "").lower()

        if content_type.startswith("application/json"):
            payload = Base64FilePayload.model_validate(await request.json())
            content_bytes, filename, _ = decode_base64_file(payload)
            return save_uploaded_document(
                file_name=filename,
                content_bytes=content_bytes,
                provider=provider,
                metadata_json=payload.metadata_json,
            )

        if file is None:
            raise HTTPException(
                status_code=400,
                detail="Multipart upload requires a file field named 'file'.",
            )

        filename = file.filename or ""
        extension = detect_supported_extension(filename)
        if extension in {".pdf", ".docx"}:
            raise HTTPException(
                status_code=400,
                detail="PDF and DOCX uploads must use the Base64 JSON upload flow.",
            )
        content = await file.read()
        parsed_metadata: dict[str, str] | None = None
        if metadata_json:
            try:
                parsed = json.loads(metadata_json)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="metadata_json must be valid JSON.") from exc
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=400, detail="metadata_json must be a JSON object.")
            parsed_metadata = {
                str(key).strip(): str(value).strip()
                for key, value in parsed.items()
                if str(key).strip() and str(value).strip()
            }
        return save_uploaded_document(
            file_name=filename,
            content_bytes=content,
            provider=provider,
            metadata_json=parsed_metadata,
        )
    except HTTPException:
        raise
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PostgresServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except StorageUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Postgres service request failed."
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Could not reach the Postgres service.") from exc


@router.get("/base64")
def read_document_as_base64(file_path: str) -> dict:
    try:
        content_bytes, filename, content_type = read_remote_document_bytes(file_path=file_path)
        return base64_payload_from_bytes(
            content_bytes,
            filename=filename,
            content_type=content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except StorageDownloadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
