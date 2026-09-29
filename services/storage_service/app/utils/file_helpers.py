from __future__ import annotations

import hashlib
import uuid
from pathlib import PurePosixPath

from fastapi import UploadFile


def generate_file_hash(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()


def generate_document_id() -> str:
    return str(uuid.uuid4())


def generate_processing_id() -> str:
    return str(uuid.uuid4())


def get_safe_file_name(file: UploadFile) -> str:
    if not file.filename:
        return "uploaded_file"
    return PurePosixPath(file.filename).name


def get_doc_type(file_name: str) -> str | None:
    suffix = PurePosixPath(file_name).suffix.lower().replace(".", "")
    return suffix or None


def build_uploaded_document_metadata(file: UploadFile, content: bytes) -> dict:
    file_name = get_safe_file_name(file)
    return {
        "document_id": generate_document_id(),
        "file_name": file_name,
        "mime_type": file.content_type,
        "doc_type": get_doc_type(file_name),
        "file_hash": generate_file_hash(content),
    }