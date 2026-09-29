from datetime import datetime
from typing import Literal

from pydantic import BaseModel


ProviderName = Literal["onedrive", "sharepoint", "nextcloud"]


class UploadResponse(BaseModel):
    status: str
    operation: str
    provider: ProviderName
    document_id: str
    file_name: str
    file_path: str
    mime_type: str | None = None
    doc_type: str | None = None
    file_hash: str | None = None
    metadata_json: dict[str, str] | None = None


class FileInfoResponse(BaseModel):
    status: str
    operation: str
    provider: ProviderName
    document_id: str
    file_name: str
    file_path: str
    mime_type: str | None = None
    doc_type: str | None = None
    file_hash: str | None = None
    metadata_json: dict[str, str] | None = None
    document_status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DeleteResponse(BaseModel):
    status: str
    operation: str
    provider: ProviderName
    operation_id: str | None = None
    document_id: str | None = None
    file_path: str
    message: str


class OperationResponse(BaseModel):
    status: str
    operation: str
    provider: ProviderName
    operation_id: str | None = None
    document_id: str | None = None
    source_path: str | None = None
    target_path: str | None = None
    folder_name: str | None = None
    message: str


class ListResponse(BaseModel):
    status: str
    operation: str
    provider: ProviderName
    folder_path: str | None = None
    items: list[dict]
    message: str | None = None


class DocumentDbResponse(BaseModel):
    document_id: str
    storage_backend: str | None = None
    file_name: str
    file_path: str
    mime_type: str | None = None
    doc_type: str | None = None
    file_hash: str | None = None
    metadata_json: dict[str, str] | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
