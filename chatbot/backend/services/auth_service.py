"""Authentication helpers for signup and login."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from services.runtime_config import get_runtime_env

PASSWORD_ITERATIONS = 100_000


def _get_auth_secret() -> str:
    return str(get_runtime_env("CHATBOT_AUTH_SECRET", "dev-secret-change-me"))


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    password_hash = base64.urlsafe_b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${password_hash}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _, iteration_text, salt, expected_hash = stored_hash.split("$", 3)
    except ValueError:
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iteration_text),
    )
    candidate_hash = base64.urlsafe_b64encode(digest).decode("utf-8")
    return hmac.compare_digest(candidate_hash, expected_hash)


def create_access_token(*, user_id: str, email: str, expires_in_seconds: int = 86400) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": int(time.time()) + expires_in_seconds,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode("utf-8")
    signature = hmac.new(
        _get_auth_secret().encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("utf-8")
    return f"{encoded_payload}.{encoded_signature}"


def decode_access_token(token: str) -> dict | None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(
        _get_auth_secret().encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    provided_signature = base64.urlsafe_b64decode(encoded_signature.encode("utf-8"))
    if not hmac.compare_digest(expected_signature, provided_signature):
        return None

    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload.encode("utf-8")))
    except (ValueError, json.JSONDecodeError):
        return None

    if payload.get("exp", 0) < int(time.time()):
        return None

    return payload
