"""ID helpers for the Docling service."""

from __future__ import annotations

import uuid


def generate_document_id() -> str:
    return str(uuid.uuid4())


def generate_processing_id() -> str:
    return str(uuid.uuid4())
