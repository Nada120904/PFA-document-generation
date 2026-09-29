"""FastAPI entry point for the Postgres service."""

from __future__ import annotations

from fastapi import FastAPI

from services.postgres_service.api import router as postgres_router
from services.postgres_service.health import router as health_router
from services.postgres_service.logging import setup_logging
from services.service_error_tracking import make_service_error_tracking_middleware
from services.runtime_config import bind_runtime_config

setup_logging()

app = FastAPI(title="postgres-service")
app.middleware("http")(make_service_error_tracking_middleware("postgres"))
app.middleware("http")(bind_runtime_config)
app.include_router(health_router)
app.include_router(postgres_router)


@app.get("/")
def root() -> dict:
    return {"message": "Postgres service is running"}
