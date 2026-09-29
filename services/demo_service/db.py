"""SQLite persistence for the local demo API."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4


DATA_DIR = Path(os.environ.get("DEMO_DATA_DIR", Path(__file__).parent / ".local")).resolve()
FILES_DIR = DATA_DIR / "files"
GENERATED_DIR = DATA_DIR / "generated"
DB_PATH = DATA_DIR / "demo.sqlite3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def database() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def make_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return salt, digest.hex()


def valid_password(password: str, salt: str, expected: str) -> bool:
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(actual.hex(), expected)


def create_user(connection: sqlite3.Connection, *, name: str, email: str, password: str) -> str:
    user_id = str(uuid4())
    salt, password_hash = make_password(password)
    connection.execute(
        "INSERT INTO users (user_id, name, email, password_salt, password_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, name, email.lower(), salt, password_hash, now()),
    )
    return user_id


def create_token(connection: sqlite3.Connection, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    connection.execute(
        "INSERT INTO access_tokens (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, now()),
    )
    return token


def init_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    with database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS access_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                title TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chat_messages_session ON chat_messages(session_id, created_at);
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                local_name TEXT NOT NULL,
                content_type TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                storage_backend TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                status TEXT NOT NULL,
                extracted_text TEXT,
                processing_id TEXT,
                indexing_run_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS documents_status ON documents(status);
            """
        )
        has_user = connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if not has_user:
            create_user(
                connection,
                name="Demo User",
                email="demo@example.com",
                password="demo12345",
            )
