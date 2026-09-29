"""Pydantic schemas for Postgres service endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MetadataFilterRequest(BaseModel):
    filters: dict[str, list[str]]
    limit: int = 1000


class MetadataOptionsResponse(BaseModel):
    items: dict[str, list[str]]


class TableSchema(BaseModel):
    name: str
    purpose: str
    primary_key: str
    columns: list[str]


class RelationSchema(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    on_delete: str


class SchemaOverview(BaseModel):
    tables: list[TableSchema]
    relations: list[RelationSchema]


class UploadedDocumentCreate(BaseModel):
    document_id: str
    storage_backend: str | None = None
    file_name: str
    file_path: str
    mime_type: str | None = None
    doc_type: str | None = None
    file_hash: str | None = None
    metadata_json: dict | None = None
    status: str


class UploadedDocumentUpdate(BaseModel):
    storage_backend: str | None = None
    file_name: str | None = None
    file_path: str | None = None
    mime_type: str | None = None
    doc_type: str | None = None
    file_hash: str | None = None
    metadata_json: dict | None = None
    status: str | None = None


class UploadedDocumentRead(BaseModel):
    document_id: str
    storage_backend: str | None = None
    file_name: str
    file_path: str
    mime_type: str | None = None
    doc_type: str | None = None
    file_hash: str | None = None
    metadata_json: dict | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DocumentProcessingCreate(BaseModel):
    processing_id: str
    document_id: str
    processing_status: str

    parsed_at: datetime | None = None
    parser_name: str | None = None
    parser_version: str | None = None

    used_ocr: bool | None = None
    ocr_engine: str | None = None
    ocr_confidence: float | None = None
    layout_confidence: float | None = None
    parse_confidence: float | None = None
    table_confidence: float | None = None
    mean_confidence: float | None = None
    low_confidence: float | None = None

    used_vlm: bool | None = None
    vlm_model: str | None = None
    markdown_text: str | None = None
    vlm_started_at: datetime | None = None
    vlm_processing_time: float | None = None


class DocumentProcessingUpdate(BaseModel):
    processing_status: str | None = None

    parsed_at: datetime | None = None
    parser_name: str | None = None
    parser_version: str | None = None

    used_ocr: bool | None = None
    ocr_engine: str | None = None
    ocr_confidence: float | None = None
    layout_confidence: float | None = None
    parse_confidence: float | None = None
    table_confidence: float | None = None
    mean_confidence: float | None = None
    low_confidence: float | None = None

    used_vlm: bool | None = None
    vlm_model: str | None = None
    markdown_text: str | None = None
    vlm_started_at: datetime | None = None
    vlm_processing_time: float | None = None


class DocumentProcessingRead(BaseModel):
    processing_id: str
    document_id: str
    processing_status: str

    parsed_at: datetime | None = None
    parser_name: str | None = None
    parser_version: str | None = None

    used_ocr: bool | None = None
    ocr_engine: str | None = None
    ocr_confidence: float | None = None
    layout_confidence: float | None = None
    parse_confidence: float | None = None
    table_confidence: float | None = None
    mean_confidence: float | None = None
    low_confidence: float | None = None

    used_vlm: bool | None = None
    vlm_model: str | None = None
    markdown_text: str | None = None
    vlm_started_at: datetime | None = None
    vlm_processing_time: float | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class FilePathsMapRequest(BaseModel):
    file_paths: list[str]


class FilePathsMapResponse(BaseModel):
    items: dict[str, str]


class DocumentStatusUpdate(BaseModel):
    status: str


class DocumentIdsListItem(BaseModel):
    document_id: str


class IndexableStatusesRequest(BaseModel):
    statuses: list[str]
    limit: int = 200


class IndexingRunCreate(BaseModel):
    document_id: str
    pipeline_mode: str | None = None
    status: str


class IndexingRunUpdate(BaseModel):
    status: str | None = None
    engine_name: str | None = None
    engine_version: str | None = None
    indexed_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    output_summary: str | None = None
    run_metadata: dict | None = None


class IndexingRunRead(BaseModel):
    indexing_run_id: str
    document_id: str
    pipeline_mode: str | None = None
    status: str
    engine_name: str | None = None
    engine_version: str | None = None
    indexed_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    output_summary: str | None = None
    run_metadata: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class RunIdResponse(BaseModel):
    run_id: str


class RetrievalRunCreate(BaseModel):
    query_text: str
    mode: str | None = None
    status: str
    top_k: int | None = None
    filters: dict | None = None
    document_id: str | None = None


class RetrievalRunUpdate(BaseModel):
    document_id: str | None = None
    status: str | None = None
    latency_ms: int | None = None
    error_message: str | None = None
    response_text: str | None = None
    score: float | None = None
    retrieved_at: datetime | None = None
    run_metadata: dict | None = None


class RetrievalRunRead(BaseModel):
    retrieval_run_id: str
    document_id: str | None = None
    mode: str | None = None
    status: str
    query_text: str
    top_k: int | None = None
    filters: dict | None = None
    latency_ms: int | None = None
    error_message: str | None = None
    response_text: str | None = None
    score: float | None = None
    retrieved_at: datetime | None = None
    run_metadata: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ServiceErrorCreate(BaseModel):
    service_name: str
    operation_name: str | None = None
    status: str | None = None
    error_message: str | None = None
    error_context: dict | None = None
    retry_count: int = 0
    duration_ms: int | None = None

    document_id: str | None = None
    processing_id: str | None = None
    indexing_run_id: str | None = None
    retrieval_run_id: str | None = None
    query_run_id: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None

    resolved_at: datetime | None = None


class ServiceErrorUpdate(BaseModel):
    service_name: str | None = None
    operation_name: str | None = None
    status: str | None = None
    error_message: str | None = None
    error_context: dict | None = None
    retry_count: int | None = None
    duration_ms: int | None = None

    document_id: str | None = None
    processing_id: str | None = None
    indexing_run_id: str | None = None
    retrieval_run_id: str | None = None
    query_run_id: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None

    resolved_at: datetime | None = None


class ServiceErrorRead(BaseModel):
    error_id: str
    service_name: str
    operation_name: str | None = None
    status: str | None = None
    error_message: str | None = None
    error_context: dict | None = None
    retry_count: int
    duration_ms: int | None = None

    document_id: str | None = None
    processing_id: str | None = None
    indexing_run_id: str | None = None
    retrieval_run_id: str | None = None
    query_run_id: str | None = None
    session_id: str | None = None
    message_id: str | None = None
    user_id: str | None = None

    created_at: datetime | None = None
    resolved_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    user_id: str
    name: str
    email: str
    password_hash: str


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    password_hash: str | None = None


class UserRead(BaseModel):
    user_id: str
    name: str
    email: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserAuthRead(BaseModel):
    user_id: str
    name: str
    email: str
    password_hash: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatSessionCreate(BaseModel):
    session_id: str
    user_id: str
    title: str | None = None
    status: str


class ChatSessionUpdate(BaseModel):
    title: str | None = None
    status: str | None = None


class ChatSessionRead(BaseModel):
    session_id: str
    user_id: str
    title: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ChatMessageCreate(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str


class ChatMessageRead(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConversationSummaryCreate(BaseModel):
    summary_id: str
    session_id: str
    summary_text: str
    version: int = 1


class ConversationSummaryUpdate(BaseModel):
    summary_text: str | None = None
    version: int | None = None


class ConversationSummaryRead(BaseModel):
    summary_id: str
    session_id: str
    summary_text: str
    version: int
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemoryRecordCreate(BaseModel):
    memory_id: str
    user_id: str
    session_id: str | None = None
    source_message_id: str | None = None
    memory_type: str
    confidence: float | None = None
    is_active: bool = True


class MemoryRecordUpdate(BaseModel):
    memory_type: str | None = None
    confidence: float | None = None
    is_active: bool | None = None


class MemoryRecordRead(BaseModel):
    memory_id: str
    user_id: str
    session_id: str | None = None
    source_message_id: str | None = None
    memory_type: str
    confidence: float | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemoryEmbeddingCreate(BaseModel):
    embedding_id: str
    memory_id: str
    qdrant_point_id: str
    embedding_model: str


class MemoryEmbeddingRead(BaseModel):
    embedding_id: str
    memory_id: str
    qdrant_point_id: str
    embedding_model: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemoryEventCreate(BaseModel):
    event_id: str
    memory_id: str
    event_type: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None


class MemoryEventRead(BaseModel):
    event_id: str
    memory_id: str
    event_type: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class QueryOptimizationRunCreate(BaseModel):
    query_run_id: str
    session_id: str | None = None
    user_id: str | None = None
    original_query: str
    optimized_query: str
    route_type: str
    strategy: str | None = None
    confidence: float | None = None
    variants: list[str] | None = None
    sub_questions: list[str] | None = None
    used_llm: bool = False
    llm_model: str | None = None
    reason: str | None = None


class QueryOptimizationRunRead(BaseModel):
    query_run_id: str
    session_id: str | None = None
    user_id: str | None = None
    original_query: str
    optimized_query: str
    route_type: str
    strategy: str | None = None
    confidence: float | None = None
    variants: list[str] | None = None
    sub_questions: list[str] | None = None
    used_llm: bool
    llm_model: str | None = None
    reason: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
