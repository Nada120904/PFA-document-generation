"""Minimal chatbot backend entrypoint scaffold."""

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from chatbot.backend.api.auth import router as auth_router
from chatbot.backend.api.chat import router as chat_router
from chatbot.backend.api.memory import router as memory_router
from chatbot.backend.api.upload import router as upload_router
from services.service_error_tracking import make_service_error_tracking_middleware
from services.runtime_config import bind_runtime_config

from chatbot.backend.api.generate import router as generate_router


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_chatbot_logging_configured", False):
        return

    level = logging.INFO
    if root_logger.handlers:
        root_logger.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(levelname)s | %(name)s | %(message)s",
        )

    logging.getLogger("chatbot").setLevel(level)
    setattr(root_logger, "_chatbot_logging_configured", True)


load_dotenv(Path(__file__).resolve().parent / ".env")
_configure_logging()

app = FastAPI(title="chatbot-backend")
app.middleware("http")(make_service_error_tracking_middleware("chatbot"))
app.middleware("http")(bind_runtime_config)
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(memory_router)
app.include_router(generate_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
