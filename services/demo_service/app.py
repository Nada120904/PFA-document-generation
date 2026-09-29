"""One-process, offline API for demonstrating the RAG workspace locally.

This module intentionally mirrors the frontend's existing HTTP contracts. It does
not start or impersonate the production document, vector, storage, or OCR services.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import re
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services.demo_service.db import (
    FILES_DIR,
    GENERATED_DIR,
    create_token,
    create_user,
    database,
    init_database,
    now,
    valid_password,
)
from services.demo_service.files import extract_text, make_generated_file, safe_filename
from services.generated_viewer import open_generated_file


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PROVIDERS = {"nextcloud", "onedrive", "sharepoint"}
GENERATED_NAME = re.compile(r"^[0-9a-f]{32}\.(pdf|docx|txt|csv)$")
WORDS = re.compile(r"\w+", re.UNICODE)
STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "document", "documents", "for", "from", "how", "i", "in", "is", "it", "me",
    "of", "on", "or", "our", "please", "say", "show", "tell", "the", "their",
    "this", "to", "us", "was", "what", "when", "where", "which", "who", "why",
    "with", "you",
}
GENERATION_WORDS = {
    "generate", "create", "make", "write", "export", "download", "pdf", "docx",
    "txt", "csv", "file", "files", "upload", "uploaded", "index", "indexed",
    "summary", "summarize", "report", "note", "notes", "content", "source", "sources",
    "only", "using", "based", "information", "data", "all", "everything",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    yield


app = FastAPI(title="RAG Workspace Local Demo", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=6, max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=20_000)
    filters: dict[str, list[str]] | None = None


class ProcessRequest(BaseModel):
    file_path: str
    language_hint: str = "auto"


class IndexRequest(BaseModel):
    file_path: str


class DeleteRequest(BaseModel):
    document_id: str | None = None
    file_path: str | None = None
    delete_storage_file: bool = True
    delete_lightrag: bool = True
    delete_project_postgres: bool = True
    delete_llm_cache: bool = False


def _user_from_token(authorization: str | None) -> dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to use this local demo.")
    token = authorization[7:].strip()
    with database() as connection:
        row = connection.execute(
            "SELECT u.user_id, u.name, u.email FROM access_tokens t "
            "JOIN users u ON u.user_id = t.user_id WHERE t.token = ?",
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Your demo session has expired. Sign in again.")
    return dict(row)


def _document_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    metadata = json.loads(row["metadata_json"] or "{}")
    return {
        "document_id": row["document_id"],
        "file_name": row["file_name"],
        "filename": row["file_name"],
        "original_filename": row["file_name"],
        "file_path": row["file_path"],
        "content_type": row["content_type"],
        "file_size": row["file_size"],
        "storage_backend": row["storage_backend"],
        "metadata_json": metadata,
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "demo_mode": True,
    }


def _processing_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None or not row["processing_id"]:
        return None
    return {
        "processing_id": row["processing_id"],
        "document_id": row["document_id"],
        "processing_status": "parsed" if row["extracted_text"] else "error",
        "markdown_text": row["extracted_text"],
        "used_vlm": False,
        "updated_at": row["updated_at"],
    }


def _indexing_from_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None or not row["indexing_run_id"]:
        return None
    return {
        "document_id": row["document_id"],
        "run_id": row["indexing_run_id"],
        "status": "indexed",
        "indexed_at": row["updated_at"],
        "demo_mode": True,
    }


def _state(row: sqlite3.Row | None) -> dict[str, Any]:
    return {
        "uploaded_document": _document_from_row(row),
        "latest_processing": _processing_from_row(row),
        "indexing_result": _indexing_from_row(row),
    }


def _get_document(*, document_id: str | None = None, file_path: str | None = None) -> sqlite3.Row | None:
    with database() as connection:
        if document_id:
            return connection.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
        if file_path:
            return connection.execute("SELECT * FROM documents WHERE file_path = ?", (file_path,)).fetchone()
    return None


def _require_document(*, document_id: str | None = None, file_path: str | None = None) -> sqlite3.Row:
    row = _get_document(document_id=document_id, file_path=file_path)
    if row is None:
        raise HTTPException(status_code=404, detail="Demo document not found.")
    return row


def _save_upload(
    *, filename: str, data: bytes, content_type: str, provider: str,
    metadata: dict[str, str],
) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Unknown storage provider selection.")
    if not data:
        raise HTTPException(status_code=400, detail="File is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Demo uploads are limited to 25 MB.")
    filename = safe_filename(filename)
    file_hash = hashlib.sha256(data).hexdigest()
    with database() as connection:
        existing = connection.execute(
            "SELECT document_id FROM documents WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"This document already exists: document_id={existing['document_id']}",
            )
        document_id = str(uuid4())
        local_name = f"{uuid4().hex}{Path(filename).suffix.lower()}"
        file_path = f"demo://{document_id}/{filename}"
        timestamp = now()
        (FILES_DIR / local_name).write_bytes(data)
        connection.execute(
            "INSERT INTO documents (document_id, file_hash, file_name, file_path, local_name, "
            "content_type, file_size, storage_backend, metadata_json, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id, file_hash, filename, file_path, local_name,
                content_type or "application/octet-stream", len(data),
                f"local-demo:{provider}", json.dumps(metadata, ensure_ascii=False),
                "uploaded", timestamp, timestamp,
            ),
        )
        row = connection.execute(
            "SELECT * FROM documents WHERE document_id = ?", (document_id,)
        ).fetchone()
    return _document_from_row(row) or {}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "demo_mode": True, "storage": "local SQLite and files"}


@app.post("/auth/signup", status_code=201)
def signup(payload: SignupRequest) -> dict[str, str]:
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if "@" not in email or not name:
        raise HTTPException(status_code=400, detail="Enter a name and valid email address.")
    try:
        with database() as connection:
            user_id = create_user(connection, name=name, email=email, password=payload.password)
            token = create_token(connection, user_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from exc
    return {"user_id": user_id, "name": name, "email": email, "access_token": token, "token_type": "bearer"}


@app.post("/auth/login")
def login(payload: LoginRequest) -> dict[str, str]:
    with database() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ?", (payload.email.strip().lower(),)
        ).fetchone()
        if row is None or not valid_password(
            payload.password, row["password_salt"], row["password_hash"]
        ):
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        token = create_token(connection, row["user_id"])
    return {
        "user_id": row["user_id"], "name": row["name"], "email": row["email"],
        "access_token": token, "token_type": "bearer",
    }


@app.get("/auth/me")
def me(authorization: str | None = Header(default=None)) -> dict[str, str]:
    return _user_from_token(authorization)


@app.get("/chat/sessions")
def list_sessions(authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    user = _user_from_token(authorization)
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
            (user["user_id"],),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/chat/sessions/{session_id}/messages")
def list_messages(session_id: str, authorization: str | None = Header(default=None)) -> list[dict[str, Any]]:
    user = _user_from_token(authorization)
    with database() as connection:
        session = connection.execute(
            "SELECT 1 FROM chat_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user["user_id"]),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        rows = connection.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at, rowid",
            (session_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.delete("/chat/sessions/{session_id}")
def delete_session(session_id: str, authorization: str | None = Header(default=None)) -> dict[str, str]:
    user = _user_from_token(authorization)
    with database() as connection:
        removed = connection.execute(
            "DELETE FROM chat_sessions WHERE session_id = ? AND user_id = ?",
            (session_id, user["user_id"]),
        ).rowcount
    if not removed:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return {"session_id": session_id}


def _terms(text: str) -> set[str]:
    result: set[str] = set()
    for raw in WORDS.findall(text):
        term = raw.lower().strip("'-")
        if len(term) <= 1 or term in STOPWORDS:
            continue
        # A small, predictable normalizer helps common questions match
        # "supports" and "supported" without needing an embedding model.
        if len(term) > 5 and term.endswith("ed"):
            term = term[:-2]
        elif len(term) > 4 and term.endswith("s") and not term.endswith("ss"):
            term = term[:-1]
        result.add(term)
    return result


def _matching_documents(filters: dict[str, list[str]] | None) -> list[sqlite3.Row]:
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM documents WHERE status = 'indexed' ORDER BY updated_at DESC"
        ).fetchall()
    if not filters:
        return rows
    result: list[sqlite3.Row] = []
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        if all(
            str(metadata.get(key, "")).casefold() in {value.casefold() for value in values}
            for key, values in filters.items() if values
        ):
            result.append(row)
    return result


def _ranked_excerpts(query: str, rows: list[sqlite3.Row]) -> list[tuple[int, str, str]]:
    query_terms = _terms(query)
    ranked: list[tuple[int, str, str]] = []
    for row in rows:
        text = row["extracted_text"] or ""
        passages = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
        if not passages:
            continue
        for passage_index, passage in enumerate(passages[:1500]):
            if passage.casefold().startswith("demo run id:"):
                continue
            if passage_index == 0 and len(passage) < 85 and not re.search(r"[.!?;:]$", passage):
                continue
            overlap = len(query_terms & _terms(passage))
            title_overlap = len(query_terms & _terms(row["file_name"]))
            score = overlap * 3 + title_overlap
            ranked.append((score, row["file_name"], passage[:550]))
    ranked.sort(key=lambda item: item[0], reverse=True)
    unique: list[tuple[int, str, str]] = []
    seen_passages: set[str] = set()
    for item in ranked:
        passage_key = re.sub(r"\s+", " ", item[2]).casefold()
        if passage_key in seen_passages:
            continue
        seen_passages.add(passage_key)
        unique.append(item)
    return unique


def _answer(query: str, filters: dict[str, list[str]] | None) -> str:
    rows = _matching_documents(filters)
    if not rows:
        if filters:
            return "No indexed documents match the selected filters in this local demo."
        return "No indexed documents yet. Upload, process, and index a document, then ask again."
    topic_terms = _terms(query) - {"upload", "uploaded", "file", "files", "index", "indexed"}
    ranked = _ranked_excerpts(" ".join(topic_terms), rows)
    if not ranked:
        return "The indexed documents contain no extractable text for this question."
    matched = [item for item in ranked if item[0] > 0][:3]
    if not matched:
        # Generic requests such as "summarize the uploaded file" should still be useful.
        if topic_terms and not any(word in query.lower() for word in ("summar", "overview", "about", "content")):
            return "I could not find that in the indexed documents. Try another question or filter."
        matched = ranked[:2]
    unique: list[tuple[int, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in matched:
        identity = (item[1], item[2])
        if identity not in seen:
            seen.add(identity)
            unique.append(item)
    lines = [f"- **{filename}:** {passage}" for _, filename, passage in unique]
    return "From the indexed local documents:\n\n" + "\n".join(lines)


def _generation_format(message: str) -> str | None:
    normalized = message.lower()
    if not re.search(r"\b(generate|create|make|write|export|download)\b", normalized):
        return None
    match = re.search(r"\b(pdf|docx|txt|csv)\b", normalized)
    return match.group(1) if match else None


def _generate_answer(message: str, format_name: str, filters: dict[str, list[str]] | None) -> str:
    rows = _matching_documents(filters)
    if not rows:
        return "There are no indexed files, so I did not generate a file. Upload and index a relevant document first."
    topic_terms = _terms(message) - GENERATION_WORDS
    subject_match = re.search(r"\b(?:about|on)\s+(.+?)(?:\s+(?:from|using)\b|[.!?]|$)", message, re.IGNORECASE)
    subject_terms = _terms(subject_match.group(1)) - GENERATION_WORDS if subject_match else set()
    if subject_terms:
        indexed_terms = set().union(*(_terms(row["extracted_text"] or "") for row in rows))
        if not subject_terms.issubset(indexed_terms):
            return "There is no data in the indexed files about that subject, so I did not generate a file."
    ranked = _ranked_excerpts(" ".join(topic_terms), rows) if topic_terms else _ranked_excerpts("", rows)
    candidates = [item for item in ranked if item[0] > 0] if topic_terms else ranked
    if subject_terms:
        candidates = [item for item in candidates if _terms(item[2]) & subject_terms]
    by_source: dict[str, list[tuple[int, str, str]]] = {}
    for item in candidates:
        by_source.setdefault(item[1], []).append(item)
    selected: list[tuple[int, str, str]] = []
    for passage_index in range(9):
        for source_items in by_source.values():
            if passage_index < len(source_items):
                selected.append(source_items[passage_index])
            if len(selected) >= 36:
                break
        if len(selected) >= 36:
            break
    if not selected:
        return (
            "There is no data in the indexed files about that subject, so I did not "
            "generate a file. Ask about a topic present in those files."
        )
    source_lines = [f"{name}: {passage}" for _, name, passage in selected]
    if subject_terms == {"ml"} or topic_terms == {"ml"}:
        title = "Machine Learning Evidence Brief"
    elif subject_match and subject_match.group(1).strip():
        title = f"{subject_match.group(1).strip().title()} Evidence Brief"
    else:
        title = "Document Intelligence Evidence Report"
    filename = make_generated_file(format_name, title, source_lines)
    link = f"/api/chatbot/generate/download/{filename}"
    return (
        f"Your {format_name.upper()} file is ready. It contains excerpts from uploaded, "
        "indexed files only, with each source named.\n\n"
        f"[Download {format_name.upper()}]({link})"
    )


@app.post("/chat/message")
def send_message(payload: ChatRequest, authorization: str | None = Header(default=None)) -> dict[str, str]:
    user = _user_from_token(authorization)
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    session_id = payload.session_id or str(uuid4())
    with database() as connection:
        if payload.session_id:
            existing = connection.execute(
                "SELECT 1 FROM chat_sessions WHERE session_id = ? AND user_id = ?",
                (session_id, user["user_id"]),
            ).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Chat session not found.")
        else:
            timestamp = now()
            connection.execute(
                "INSERT INTO chat_sessions (session_id, user_id, title, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, user["user_id"], message[:72], "active", timestamp, timestamp),
            )
        connection.execute(
            "INSERT INTO chat_messages (message_id, session_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), session_id, "user", message, now()),
        )
    format_name = _generation_format(message)
    try:
        answer = (
            _generate_answer(message, format_name, payload.filters)
            if format_name else _answer(message, payload.filters)
        )
    except Exception as exc:
        # Give the user a retryable error; don't invent an answer on a generation failure.
        raise HTTPException(status_code=500, detail=f"Local demo response failed: {exc}") from exc
    with database() as connection:
        connection.execute(
            "INSERT INTO chat_messages (message_id, session_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), session_id, "assistant", answer, now()),
        )
        connection.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?", (now(), session_id)
        )
    return {"session_id": session_id, "answer": answer}


@app.get("/generate/download/{filename}")
def download_generated_file(filename: str):
    if not GENERATED_NAME.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid generated filename.")
    target = GENERATED_DIR / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Generated file not found.")
    return FileResponse(target, filename=filename)


@app.get("/generate/preview/{filename}")
def preview_generated_file(filename: str) -> dict[str, Any]:
    if not GENERATED_NAME.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid generated filename.")
    target = GENERATED_DIR / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Generated file not found.")
    data = target.read_bytes()
    result: dict[str, Any] = {
        "filename": filename, "format": target.suffix[1:],
        "text": extract_text(filename, data),
    }
    if target.suffix == ".csv":
        result["rows"] = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))[:30]
    return result


@app.get("/generate/open/{filename}")
def open_generated_file_view(filename: str):
    if not GENERATED_NAME.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid generated filename.")
    target = GENERATED_DIR / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Generated file not found.")
    return open_generated_file(target)


@app.get("/orchestration/status")
def service_status() -> dict[str, Any]:
    offline = {
        "configured": False, "reachable": False, "url": None, "payload": None,
        "error": "Production microservice is not running in standalone local demo mode.",
    }
    return {
        "demo_mode": True,
        "orchestration": {
            "configured": True, "reachable": True, "url": "local demo API",
            "payload": {"status": "ok", "mode": "local-demo"}, "error": None,
        },
        **{name: dict(offline) for name in ("storage", "postgres", "upload", "docling", "vlm", "lightrag")},
    }


@app.post("/orchestration/postgres/init")
def initialize_demo_database() -> dict[str, Any]:
    init_database()
    return {"status": "ok", "demo_mode": True, "message": "Local SQLite is ready."}


@app.post("/documents/upload")
@app.post("/orchestration/upload")
async def upload_document(
    request: Request,
    provider: str = Query(default="nextcloud"),
    file: UploadFile | None = File(default=None),
    metadata_json: str | None = Form(default=None),
) -> dict[str, Any]:
    content_type_header = request.headers.get("content-type", "").lower()
    if content_type_header.startswith("application/json"):
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object.")
            filename = str(payload.get("filename", ""))
            encoded = payload.get("base64_data", payload.get("content_base64", ""))
            data = base64.b64decode(encoded, validate=True)
            declared_size = payload.get("size_bytes")
            if declared_size is not None and int(declared_size) != len(data):
                raise ValueError("Declared file size does not match decoded data.")
            metadata = payload.get("metadata_json") or {}
            content_type = str(payload.get("content_type") or payload.get("mime_type") or "application/octet-stream")
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Base64 upload: {exc}") from exc
    else:
        if file is None:
            raise HTTPException(status_code=400, detail="Upload requires a file field.")
        filename = file.filename or "document"
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        content_type = file.content_type or "application/octet-stream"
        try:
            metadata = json.loads(metadata_json) if metadata_json else {}
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="metadata_json must be valid JSON.") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata_json must be an object.")
    clean_metadata = {
        str(key).strip(): str(value).strip() for key, value in metadata.items()
        if str(key).strip() and str(value).strip()
    }
    return _save_upload(
        filename=filename, data=data, content_type=content_type,
        provider=provider, metadata=clean_metadata,
    )


@app.get("/orchestration/documents")
def list_documents(limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_document_from_row(row) or {} for row in rows]


@app.get("/orchestration/document-metadata/options")
def metadata_options() -> dict[str, dict[str, list[str]]]:
    with database() as connection:
        rows = connection.execute("SELECT metadata_json FROM documents").fetchall()
    values: dict[str, set[str]] = {}
    for row in rows:
        for key, value in json.loads(row["metadata_json"] or "{}").items():
            values.setdefault(key, set()).add(str(value))
    return {"items": {key: sorted(items) for key, items in sorted(values.items())}}


@app.get("/orchestration/document-state")
def document_state(file_path: str) -> dict[str, Any]:
    return _state(_get_document(file_path=file_path))


@app.get("/orchestration/document-state/by-document-id")
def document_state_by_id(document_id: str) -> dict[str, Any]:
    return _state(_get_document(document_id=document_id))


@app.post("/orchestration/process")
def process_document(payload: ProcessRequest) -> dict[str, Any]:
    row = _require_document(file_path=payload.file_path)
    if row["extracted_text"]:
        return {
            "uploaded_document": _document_from_row(row),
            "docling_result": {"status": "parsed", "mode": "local-demo"},
            "latest_processing": _processing_from_row(row),
            "confidence_source": "local text extraction", "confidence_value": None,
            "vlm_triggered": False, "vlm_result": None,
            "final_markdown": row["extracted_text"],
            "final_message": "Document text was already extracted in local demo mode.",
        }
    processing_id = str(uuid4())
    try:
        text = extract_text(row["file_name"], (FILES_DIR / row["local_name"]).read_bytes())
    except Exception as exc:
        with database() as connection:
            connection.execute(
                "UPDATE documents SET processing_id = ?, status = 'error', updated_at = ? "
                "WHERE document_id = ?", (processing_id, now(), row["document_id"]),
            )
        raise HTTPException(status_code=422, detail=f"Local demo extraction failed: {exc}") from exc
    with database() as connection:
        connection.execute(
            "UPDATE documents SET extracted_text = ?, processing_id = ?, status = 'parsed', "
            "updated_at = ? WHERE document_id = ?",
            (text, processing_id, now(), row["document_id"]),
        )
        updated = connection.execute(
            "SELECT * FROM documents WHERE document_id = ?", (row["document_id"],)
        ).fetchone()
    return {
        "uploaded_document": _document_from_row(updated),
        "docling_result": {"status": "parsed", "mode": "local-demo"},
        "latest_processing": _processing_from_row(updated),
        "confidence_source": "local text extraction", "confidence_value": None,
        "vlm_triggered": False, "vlm_result": None,
        "final_markdown": text,
        "final_message": "Document text extracted locally. Ready to index.",
    }


@app.post("/orchestration/lightrag/index-by-path")
def index_document(payload: IndexRequest) -> dict[str, Any]:
    row = _require_document(file_path=payload.file_path)
    if not row["extracted_text"]:
        raise HTTPException(status_code=409, detail="Process the document before indexing it.")
    run_id = row["indexing_run_id"] or str(uuid4())
    with database() as connection:
        connection.execute(
            "UPDATE documents SET status = 'indexed', indexing_run_id = ?, updated_at = ? "
            "WHERE document_id = ?", (run_id, now(), row["document_id"]),
        )
        updated = connection.execute(
            "SELECT * FROM documents WHERE document_id = ?", (row["document_id"],)
        ).fetchone()
    return {
        "file_path": row["file_path"], "document_id": row["document_id"],
        "indexing_result": _indexing_from_row(updated), "demo_mode": True,
    }


@app.post("/orchestration/document/delete")
def delete_document(payload: DeleteRequest) -> dict[str, Any]:
    row = _require_document(document_id=payload.document_id, file_path=payload.file_path)
    with database() as connection:
        connection.execute("DELETE FROM documents WHERE document_id = ?", (row["document_id"],))
    (FILES_DIR / row["local_name"]).unlink(missing_ok=True)
    return {
        "status": "deleted", "document_id": row["document_id"],
        "file_path": row["file_path"],
        "storage_delete_result": {"status": "deleted", "mode": "local-demo"},
        "lightrag_delete_result": {"status": "removed", "mode": "local lexical search"},
        "postgres_purge_result": {"status": "deleted", "mode": "local SQLite"},
        "errors": [], "chatbot_visibility": "removed from local demo search",
    }
