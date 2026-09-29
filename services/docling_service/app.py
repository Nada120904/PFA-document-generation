"""FastAPI entry point for the Docling service container."""

from __future__ import annotations

from fastapi import FastAPI

from services.docling_service.health import router as health_router
from services.docling_service.api import router as docling_router
from services.docling_service.logging import setup_logging
from services.service_error_tracking import make_service_error_tracking_middleware
from services.runtime_config import bind_runtime_config

setup_logging()

app = FastAPI(title="docling-service")
app.middleware("http")(make_service_error_tracking_middleware("docling"))
app.middleware("http")(bind_runtime_config)
app.include_router(health_router)
app.include_router(docling_router)


@app.get("/")
def root() -> dict:
    return {"message": "Docling service is running"}
