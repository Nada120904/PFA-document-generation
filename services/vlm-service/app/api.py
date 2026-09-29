from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status

from app.app import create_app
from app.config import get_settings
from app.logging import get_logger
from app.process_document import ProcessDocumentService
from app.runtime_config import (
    extract_runtime_overrides,
    use_runtime_overrides,
)
from app.schemas import HealthResponse, ProcessCheckResponse, ProcessDocumentResponse

logger = get_logger(__name__)

app: FastAPI = create_app()


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health(request: Request) -> HealthResponse:
    with use_runtime_overrides(extract_runtime_overrides(request.headers)):
        settings = get_settings()

        return HealthResponse(
            status="ok",
            service=settings.app_name,
            environment=settings.environment,
            postgres_service_url=settings.postgres_service_url,
            base_url=settings.base_url,
            model_id=settings.model_id,
        )


@app.post(
    "/vlm/process-document/{processing_id}",
    response_model=ProcessDocumentResponse,
    tags=["VLM Processing"],
)
def process_document(
    request: Request,
    processing_id: str,
    background_tasks: BackgroundTasks,
) -> ProcessDocumentResponse:
    overrides = extract_runtime_overrides(request.headers)
    try:
        with use_runtime_overrides(overrides):
            service = ProcessDocumentService()
            effective_settings = get_settings()
            logger.info(
                "VLM trigger received runtime overrides | processing_id=%s | override_keys=%s | postgres_service_url=%s | storage_service_url=%s",
                processing_id,
                sorted(overrides.keys()),
                effective_settings.postgres_service_url,
                effective_settings.storage_service_url,
            )
            result = service.enqueue_processing(processing_id)

        background_tasks.add_task(
            service.process_in_background,
            processing_id,
            overrides,
        )

        return ProcessDocumentResponse(**result)

    except Exception as exc:
        logger.error(
            "Could not enqueue VLM processing | processing_id=%s | error=%s",
            processing_id,
            exc,
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@app.post(
    "/vlm/process-document-by-id/{document_id}",
    response_model=ProcessDocumentResponse,
    tags=["VLM Processing"],
)
def process_document_by_document_id(
    request: Request,
    document_id: str,
    background_tasks: BackgroundTasks,
) -> ProcessDocumentResponse:
    overrides = extract_runtime_overrides(request.headers)
    try:
        with use_runtime_overrides(overrides):
            service = ProcessDocumentService()
            result = service.enqueue_processing_by_document_id(document_id)

        background_tasks.add_task(
            service.process_in_background,
            result["processing_id"],
            overrides,
        )

        return ProcessDocumentResponse(**result)

    except Exception as exc:
        logger.error(
            "Could not enqueue VLM processing by document_id | document_id=%s | error=%s",
            document_id,
            exc,
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@app.get(
    "/vlm/process-check/{processing_id}",
    response_model=ProcessCheckResponse,
    tags=["VLM Processing"],
)
def process_check(
    request: Request,
    processing_id: str,
) -> ProcessCheckResponse:
    try:
        with use_runtime_overrides(extract_runtime_overrides(request.headers)):
            service = ProcessDocumentService()
            result = service.check_processing(processing_id)
            return ProcessCheckResponse(**result)

    except Exception as exc:
        logger.error(
            "Could not check VLM processing | processing_id=%s | error=%s",
            processing_id,
            exc,
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
