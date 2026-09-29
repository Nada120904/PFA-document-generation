"""Plain text (.txt) generation service."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from services.evidence_export import evidence_from_lines, write_txt

logger = logging.getLogger(__name__)

GENERATED_FILES_DIR = Path(__file__).resolve().parent.parent / "generated_files"
GENERATED_FILES_DIR.mkdir(parents=True, exist_ok=True)


def generate_txt(params: dict, body_paragraphs: list[str], source_note: str) -> str:
    filename = f"{uuid.uuid4().hex}.txt"
    file_path = GENERATED_FILES_DIR / filename

    title = str(params.get("topic") or params.get("title") or "Generated Document")
    write_txt(file_path, title, evidence_from_lines(body_paragraphs))
    logger.info("txt_generator.generated filename=%s paragraphs=%s", filename, len(body_paragraphs))
    return filename
