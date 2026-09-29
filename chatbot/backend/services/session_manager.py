"""Session manager scaffold."""

from __future__ import annotations

import uuid

from chatbot.backend.services.service_clients import postgres_get, postgres_patch, postgres_post


def create_session_title(first_message: str) -> str:
    text = first_message.strip() or "New chat"
    return text[:60]


def ensure_session_id(session_id: str | None) -> str:
    return (session_id or "").strip() or "new-session"


def load_or_create_session(*, user_id: str, session_id: str | None, first_message: str) -> dict[str, object]:
    requested_session_id = (session_id or "").strip()
    if requested_session_id:
        status_code, payload = postgres_get(f"/db/chat-sessions/{requested_session_id}")
        if status_code < 400 and isinstance(payload, dict):
            return payload

    new_session_id = str(uuid.uuid4())
    status_code, payload = postgres_post(
        "/db/chat-sessions",
        {
            "session_id": new_session_id,
            "user_id": user_id,
            "title": create_session_title(first_message),
            "status": "active",
        },
    )
    if status_code >= 400 or not isinstance(payload, dict):
        raise RuntimeError("Failed to create chat session in postgres service.")
    return payload


def load_recent_messages(*, session_id: str) -> list[dict[str, str]]:
    status_code, payload = postgres_get(f"/db/chat-sessions/{session_id}/messages")
    if status_code == 404 or not isinstance(payload, list):
        return []
    if status_code >= 400:
        raise RuntimeError("Failed to load chat messages from postgres service.")
    return [
        {
            "role": str(item.get("role", "")),
            "content": str(item.get("content", "")),
        }
        for item in payload
        if isinstance(item, dict)
    ]


def load_session_summary(*, session_id: str) -> str | None:
    record = load_session_summary_record(session_id=session_id)
    if not record:
        return None
    summary_text = record.get("summary_text")
    return str(summary_text) if summary_text else None


def load_session_summary_record(*, session_id: str) -> dict[str, object] | None:
    status_code, payload = postgres_get(f"/db/chat-sessions/{session_id}/summary")
    if status_code == 404 or not isinstance(payload, dict):
        return None
    if status_code >= 400:
        raise RuntimeError("Failed to load conversation summary from postgres service.")
    return payload


def save_session_summary(
    *,
    session_id: str,
    summary_text: str,
    summary_record: dict[str, object] | None = None,
) -> dict[str, object]:
    if summary_record and summary_record.get("summary_id"):
        current_version = int(summary_record.get("version", 1))
        status_code, payload = postgres_patch(
            f"/db/conversation-summaries/{summary_record['summary_id']}",
            {
                "summary_text": summary_text,
                "version": current_version + 1,
            },
        )
    else:
        status_code, payload = postgres_post(
            "/db/conversation-summaries",
            {
                "summary_id": str(uuid.uuid4()),
                "session_id": session_id,
                "summary_text": summary_text,
                "version": 1,
            },
        )

    if status_code >= 400 or not isinstance(payload, dict):
        raise RuntimeError("Failed to save conversation summary in postgres service.")
    return payload


def save_chat_message(*, session_id: str, role: str, content: str) -> None:
    status_code, _ = postgres_post(
        "/db/chat-messages",
        {
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": role,
            "content": content,
        },
    )
    if status_code >= 400:
        raise RuntimeError("Failed to save chat message in postgres service.")
