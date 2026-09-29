"""Chat endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from chatbot.backend.api.auth import get_current_user_from_authorization
from chatbot.backend.graph import run_chat_workflow
from chatbot.backend.models.chat import (
    ChatHistoryMessageResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionResponse,
)
from chatbot.backend.services.session_manager import save_chat_message
from chatbot.backend.services.service_clients import postgres_delete, postgres_get

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSessionResponse])
def list_sessions(authorization: str | None = Header(default=None)) -> list[ChatSessionResponse]:
    user = get_current_user_from_authorization(authorization)
    status_code, payload = postgres_get(f"/db/users/{user['user_id']}/chat-sessions")
    if status_code == 404 or not isinstance(payload, list):
        return []
    if status_code >= 400:
        return []
    return [
        ChatSessionResponse(
            session_id=str(item.get("session_id", "")),
            title=item.get("title"),
            status=str(item.get("status", "")),
            created_at=str(item.get("created_at")) if item.get("created_at") else None,
            updated_at=str(item.get("updated_at")) if item.get("updated_at") else None,
        )
        for item in payload
        if isinstance(item, dict) and item.get("session_id")
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatHistoryMessageResponse])
def list_session_messages(
    session_id: str,
    authorization: str | None = Header(default=None),
) -> list[ChatHistoryMessageResponse]:
    user = get_current_user_from_authorization(authorization)
    status_code, session_payload = postgres_get(f"/db/chat-sessions/{session_id}")
    if status_code >= 400 or not isinstance(session_payload, dict):
        return []
    if str(session_payload.get("user_id")) != str(user["user_id"]):
        return []

    status_code, payload = postgres_get(f"/db/chat-sessions/{session_id}/messages")
    if status_code == 404 or not isinstance(payload, list):
        return []
    if status_code >= 400:
        return []
    return [
        ChatHistoryMessageResponse(
            message_id=str(item.get("message_id", "")),
            session_id=str(item.get("session_id", "")),
            role=str(item.get("role", "")),
            content=str(item.get("content", "")),
            created_at=str(item.get("created_at")) if item.get("created_at") else None,
        )
        for item in payload
        if isinstance(item, dict) and item.get("message_id")
    ]


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user = get_current_user_from_authorization(authorization)
    status_code, session_payload = postgres_get(f"/db/chat-sessions/{session_id}")
    if status_code >= 400 or not isinstance(session_payload, dict):
        raise HTTPException(status_code=404, detail="Chat session not found.")
    if str(session_payload.get("user_id")) != str(user["user_id"]):
        raise HTTPException(status_code=403, detail="You cannot delete this chat session.")

    delete_status, _ = postgres_delete(f"/db/chat-sessions/{session_id}")
    if delete_status >= 400:
        raise HTTPException(status_code=500, detail="Failed to delete chat session.")
    return {"session_id": session_id}


@router.post("/message")
def send_message(
    payload: ChatMessageRequest,
    authorization: str | None = Header(default=None),
) -> ChatMessageResponse:
    user = get_current_user_from_authorization(authorization)
    workflow_input = {
        "user_id": user["user_id"],
        "session_id": payload.session_id,
        "user_message": payload.message,
        "retrieval_filters": payload.filters or {},
    }
    state = run_chat_workflow(workflow_input)

    session_id = str(state["session_id"])
    save_chat_message(session_id=session_id, role="user", content=payload.message)
    save_chat_message(session_id=session_id, role="assistant", content=str(state["answer"]))

    return ChatMessageResponse(
        session_id=session_id,
        answer=str(state["answer"]),
    )
