"""ID helpers for the upload service."""

from __future__ import annotations

import uuid


def generate_document_id() -> str:
    return str(uuid.uuid4())
