from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI

from app.config import get_settings
from app.logging import setup_logging
from app.runtime_config import bind_runtime_config
from services.service_error_tracking import make_service_error_tracking_middleware


def create_app() -> FastAPI:
    setup_logging()

    settings = get_settings()

    app = FastAPI(
        title="VLM Processing Service",
        description="OCR microservice using VLM models.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.middleware("http")(make_service_error_tracking_middleware("vlm"))
    app.middleware("http")(bind_runtime_config)

    @app.get("/")
    def root() -> dict:
        return {
            "status": "running",
            "service": settings.app_name,
            "docs": "/docs",
            "health": "/health",
        }

    return app
