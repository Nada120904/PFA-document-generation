"""Chat models scaffold."""

from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    session_id: str | None = None
    message: str
    filters: dict[str, list[str]] | None = None


class ChatMessageResponse(BaseModel):
    session_id: str
    answer: str


class ChatSessionResponse(BaseModel):
    session_id: str
    title: str | None = None
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class ChatHistoryMessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str | None = None
