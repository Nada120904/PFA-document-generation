"""Memory endpoints scaffold."""

from fastapi import APIRouter

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("/session/{session_id}/summary")
def get_session_summary(session_id: str) -> dict[str, str]:
    return {
        "session_id": session_id,
        "message": "TODO: return session summary",
    }
