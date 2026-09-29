from __future__ import annotations

from services.postgres_service.db.models import Base
from services.postgres_service.db.postgres import engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Postgres service tables created successfully.")
