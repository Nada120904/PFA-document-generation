from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DoclingTriggerRequest(BaseModel):
    file_path: str
    language_hint: str = "auto"


class OrchestrationRetrievalRequest(BaseModel):
    query: str
    top_k: int = 5
    search_type: str = "hybrid"
    generate_answer: bool = True
    evaluate_ragas: bool = False
    answer: str | None = None
    reference: str | None = None
    filters: dict[str, list[str]] | None = None


class OrchestrationDocumentDeleteRequest(BaseModel):
    document_id: str | None = None
    file_path: str | None = None
    delete_storage_file: bool = True
    delete_lightrag: bool = True
    delete_project_postgres: bool = True
    delete_llm_cache: bool = False


class ServiceCard(BaseModel):
    configured: bool
    reachable: bool
    url: str | None = None
    payload: dict[str, Any] | None = None
    error: str | None = None


class ServiceStatusResponse(BaseModel):
    orchestration: ServiceCard
    storage: ServiceCard
    postgres: ServiceCard
    upload: ServiceCard
    docling: ServiceCard
    vlm: ServiceCard
    lightrag: ServiceCard


class PipelineResponse(BaseModel):
    uploaded_document: dict[str, Any] | None = None
    docling_result: dict[str, Any] | None = None
    latest_processing: dict[str, Any] | None = None
    confidence_source: str | None = None
    confidence_value: float | None = None
    vlm_triggered: bool = False
    vlm_result: dict[str, Any] | None = None
    final_markdown: str | None = None
    final_message: str
