"""Hashing helpers for the upload service."""

from __future__ import annotations

import hashlib


def generate_file_hash(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()
