from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    postgres_service_url: str
    base_url: str
    model_id: str


class ProcessDocumentResponse(BaseModel):
    processing_id: str
    document_id: str | None = None
    status: str
    message: str


class ProcessCheckResponse(BaseModel):
    processing_id: str
    document_id: str
    processing_status: str

    used_vlm: bool | None = None
    vlm_model: str | None = None
    vlm_started_at: datetime | None = None
    vlm_processing_time: float | None = None

    markdown_text_available: bool
    markdown_text_length: int

    raw_processing: dict[str, Any]


class PostgresProcessingRow(BaseModel):
    processing_id: str
    document_id: str
    processing_status: str

    used_vlm: bool | None = None
    vlm_model: str | None = None
    markdown_text: str | None = None
    vlm_started_at: datetime | None = None
    vlm_processing_time: float | None = None


class PostgresDocumentRow(BaseModel):
    document_id: str
    file_name: str
    file_path: str
    mime_type: str | None = None
    doc_type: str | None = None
    file_hash: str | None = None
    status: str