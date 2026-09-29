"""Authentication endpoints for the chatbot backend."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Header, HTTPException, status

from chatbot.backend.models.auth import AuthResponse, CurrentUserResponse, LoginRequest, SignUpRequest
from chatbot.backend.services.auth_service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from chatbot.backend.services.service_clients import postgres_get, postgres_post

router = APIRouter(prefix="/auth", tags=["auth"])


def _read_user_by_email(email: str) -> dict | None:
    status_code, payload = postgres_get("/db/users/by-email", {"email": email})
    if status_code == 404:
        return None
    if status_code >= 400:
        raise HTTPException(status_code=502, detail="Failed to read user from postgres service.")
    return payload if isinstance(payload, dict) else None


def _read_user_by_id(user_id: str) -> dict | None:
    status_code, payload = postgres_get(f"/db/users/{user_id}")
    if status_code == 404:
        return None
    if status_code >= 400:
        raise HTTPException(status_code=502, detail="Failed to read user from postgres service.")
    return payload if isinstance(payload, dict) else None


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUpRequest) -> AuthResponse:
    existing_user = _read_user_by_email(payload.email)
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists.")

    user_id = str(uuid.uuid4())
    password_hash = hash_password(payload.password)
    status_code, created_user = postgres_post(
        "/db/users",
        {
            "user_id": user_id,
            "name": payload.name,
            "email": payload.email,
            "password_hash": password_hash,
        },
    )
    if status_code >= 400 or created_user is None:
        raise HTTPException(status_code=502, detail="Failed to create user in postgres service.")

    access_token = create_access_token(user_id=user_id, email=payload.email)
    return AuthResponse(
        user_id=created_user["user_id"],
        name=created_user["name"],
        email=created_user["email"],
        access_token=access_token,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    user = _read_user_by_email(payload.email)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    access_token = create_access_token(user_id=user["user_id"], email=user["email"])
    return AuthResponse(
        user_id=user["user_id"],
        name=user["name"],
        email=user["email"],
        access_token=access_token,
    )


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(authorization: str | None = Header(default=None)) -> CurrentUserResponse:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")

    token = authorization.removeprefix("Bearer ").strip()
    token_payload = decode_access_token(token)
    if token_payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token.")

    user = _read_user_by_id(token_payload["user_id"])
    if user is None:
        raise HTTPException(status_code=404, detail="User no longer exists.")

    return CurrentUserResponse(
        user_id=user["user_id"],
        name=user["name"],
        email=user["email"],
    )


def get_current_user_from_authorization(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header.")

    token = authorization.removeprefix("Bearer ").strip()
    token_payload = decode_access_token(token)
    if token_payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired access token.")

    user = _read_user_by_id(token_payload["user_id"])
    if user is None:
        raise HTTPException(status_code=404, detail="User no longer exists.")
    return user
