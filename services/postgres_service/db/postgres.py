from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.postgres_service.config import get_settings


def _normalize_postgres_url(postgres_url: str) -> str:
    if postgres_url.startswith("postgresql://"):
        return postgres_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return postgres_url


@lru_cache(maxsize=16)
def get_engine(postgres_url: str):
    # Keep the pool resilient in a multi-service dev setup where several workers
    # may open short-lived connections at the same time.
    return create_engine(
        _normalize_postgres_url(postgres_url),
        pool_pre_ping=True,
        pool_recycle=300,
        pool_timeout=30,
        pool_size=10,
        max_overflow=20,
    )


@lru_cache(maxsize=16)
def _build_session_local(postgres_url: str):
    engine = get_engine(postgres_url)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator:
    settings = get_settings()
    SessionLocal = _build_session_local(settings.postgres_url)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
