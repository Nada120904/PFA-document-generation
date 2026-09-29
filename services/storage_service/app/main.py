from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.files_routes import router as files_router
from .api.health_routes import router as health_router
from .logging import setup_logging
from services.runtime_config import bind_runtime_config


setup_logging()


app = FastAPI(
    title="Storage Service",
    description="Unified storage API for OneDrive, SharePoint, and Nextcloud. Database tracking is handled by postgres_service.",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(bind_runtime_config)


@app.get("/")
def root():
    return {
        "status": "running",
        "service": "storage-service",
        "docs": "/docs",
        "health": "/health",
    }


app.include_router(health_router)
app.include_router(files_router)

#uvicorn services.storage_service.app:app --host 127.0.0.1 --port 8001 --reload
