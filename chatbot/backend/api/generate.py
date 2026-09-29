"""Download endpoint for generated documents."""

from __future__ import annotations

import re
import csv
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from chatbot.backend.services.pdf_generator import GENERATED_FILES_DIR
from services.generated_viewer import open_generated_file

router = APIRouter(prefix="/generate", tags=["generate"])

_SAFE_FILENAME = re.compile(r"^[a-f0-9]{32}\.(pdf|txt|docx|csv)$")


import mimetypes

@router.get("/download/{filename}")
def download_generated_file(filename: str):
    if not _SAFE_FILENAME.match(filename):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    file_path = GENERATED_FILES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found.")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(str(file_path), media_type=media_type, filename=filename)


@router.get("/preview/{filename}")
def preview_generated_file(filename: str):
    if not _SAFE_FILENAME.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    file_path = GENERATED_FILES_DIR / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    suffix = file_path.suffix.lower()
    rows = None
    if suffix == ".txt":
        text = file_path.read_text(encoding="utf-8")
    elif suffix == ".csv":
        rows = list(csv.reader(io.StringIO(file_path.read_text(encoding="utf-8-sig"))))[:30]
        text = "\n".join(", ".join(row) for row in rows)
    elif suffix == ".docx":
        from docx import Document
        document = Document(file_path)
        text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    else:
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(file_path).pages)
    return {"filename": filename, "format": suffix[1:], "text": text[:30000], "rows": rows}


@router.get("/open/{filename}")
def open_generated_file_view(filename: str):
    if not _SAFE_FILENAME.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid filename.")
    file_path = GENERATED_FILES_DIR / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return open_generated_file(file_path)
