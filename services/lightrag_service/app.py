from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI

from services.lightrag_service.config import get_settings
from services.lightrag_service.indexing.router import router as indexing_router
from services.lightrag_service.retrieval.router import router as retrieval_router
from services.service_error_tracking import make_service_error_tracking_middleware
from services.runtime_config import bind_runtime_config


def _configure_logging() -> None:
    settings = get_settings()
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s.%(msecs)03d | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    root_logger = logging.getLogger()
    if getattr(root_logger, "_lightrag_logging_configured", False):
        return

    level_name = str(settings.log_level).upper().strip()
    level = getattr(logging, level_name, logging.INFO)
    if not isinstance(level, int):
        level = logging.INFO
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(log_dir / "lightrag_service.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    error_handler = logging.FileHandler(log_dir / "lightrag_errors.log", encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    setattr(root_logger, "_lightrag_logging_configured", True)

    # Route uvicorn logs through root handlers so file logs include access/errors too.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)


_configure_logging()

app = FastAPI(title="rag-service")
app.middleware("http")(make_service_error_tracking_middleware("lightrag"))
app.middleware("http")(bind_runtime_config)
app.include_router(indexing_router)
app.include_router(retrieval_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {"message": "RAG unified service is running"}
