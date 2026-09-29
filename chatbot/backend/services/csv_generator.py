"""Create a CSV containing only retrieved excerpts from indexed documents."""

from __future__ import annotations

import uuid
from pathlib import Path

from services.evidence_export import Evidence, write_csv

GENERATED_FILES_DIR = Path(__file__).resolve().parent.parent / "generated_files"
GENERATED_FILES_DIR.mkdir(parents=True, exist_ok=True)


def generate_csv(params: dict, chunks: list[dict]) -> tuple[str, list[list[str]]]:
    """Write source and verbatim excerpt rows; never synthesize sample data."""
    if not chunks:
        raise ValueError("No indexed source content was found.")
    filename = f"{uuid.uuid4().hex}.csv"
    file_path = GENERATED_FILES_DIR / filename
    entries: list[Evidence] = []
    for chunk in chunks:
        excerpt = str(chunk.get("content") or "").strip()
        if not excerpt:
            continue
        source = Path(str(chunk.get("file_path") or chunk.get("document_id") or "Indexed document")).name
        entries.append(Evidence(source, excerpt))
    if not entries:
        raise ValueError("Indexed results contain no extractable text.")
    rows = write_csv(file_path, entries)
    return filename, rows
