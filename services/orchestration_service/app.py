"""FastAPI entry point for the orchestration service."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from services.orchestration_service.api import router as orchestration_router
from services.orchestration_service.health import router as health_router
from services.orchestration_service.logging import setup_logging
from services.service_error_tracking import make_service_error_tracking_middleware
from services.runtime_config import bind_runtime_config

setup_logging()

app = FastAPI(title="orchestration-service")
app.middleware("http")(make_service_error_tracking_middleware("orchestration"))
app.middleware("http")(bind_runtime_config)
app.include_router(health_router)
app.include_router(orchestration_router)
app.mount(
    "/assets",
    StaticFiles(directory="services/orchestration_service/static"),
    name="assets",
)


@app.get("/api")
def root() -> dict:
    return {"message": "Orchestration service is running"}
