"""Memory models scaffold."""

from pydantic import BaseModel


class SessionSummaryResponse(BaseModel):
    session_id: str
    summary_text: str | None = None
