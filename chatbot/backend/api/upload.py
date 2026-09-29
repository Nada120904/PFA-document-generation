"""Upload endpoints scaffold for the chatbot."""

from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["upload"])


@router.post("/upload")
def upload_file() -> dict[str, str]:
    return {"message": "TODO: implement chatbot upload flow"}
