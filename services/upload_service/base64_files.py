from __future__ import annotations

import base64
import binascii
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field


class Base64FilePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filename: str
    content_type: str | None = Field(default=None, alias="mime_type")
    size_bytes: int | None = None
    base64_data: str = Field(alias="content_base64")
    metadata_json: dict[str, str] | None = None


BASE64_ALLOWED_EXTENSIONS = {".pdf", ".docx"}
BASE64_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",
}


def safe_filename(filename: str | None, fallback: str = "file") -> str:
    cleaned = Path((filename or fallback).replace("\\", "/")).name.strip()
    return cleaned or fallback


def validate_base64_file_hint(filename: str, content_type: str | None) -> str:
    extension = Path(filename).suffix.lower()
    declared_type = (content_type or "").lower().strip()

    if extension not in BASE64_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Base64 JSON upload is supported only for .pdf and .docx files."
            ),
        )

    if declared_type and declared_type not in BASE64_ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported declared content type '{declared_type}' for Base64 upload."
            ),
        )

    return extension


def decode_base64_file(
    payload: Base64FilePayload,
    *,
    max_file_bytes: int = 262_144_000,
) -> tuple[bytes, str, str]:
    filename = safe_filename(payload.filename)
    extension = validate_base64_file_hint(filename, payload.content_type)

    try:
        data = base64.b64decode(payload.base64_data.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Base64 payload for '{filename}'.",
        ) from exc

    if not data:
        raise HTTPException(status_code=400, detail=f"Empty file: '{filename}'.")
    if len(data) > max_file_bytes:
        raise HTTPException(status_code=413, detail=f"File too large: '{filename}'.")
    if payload.size_bytes is not None and payload.size_bytes != len(data):
        raise HTTPException(
            status_code=400,
            detail=f"Declared size does not match decoded size for '{filename}'.",
        )

    return data, filename, extension


def base64_payload_from_bytes(
    data: bytes,
    *,
    filename: str,
    content_type: str | None = None,
) -> dict[str, str | int | None]:
    return {
        "filename": safe_filename(filename),
        "content_type": content_type,
        "size_bytes": len(data),
        "base64_data": base64.b64encode(data).decode("ascii"),
    }
