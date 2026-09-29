"""Postgres service API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from services.postgres_service.db.postgres import get_db
from services.postgres_service.schema import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionRead,
    ChatSessionUpdate,
    ConversationSummaryCreate,
    ConversationSummaryRead,
    ConversationSummaryUpdate,
    DocumentIdsListItem,
    DocumentStatusUpdate,
    DocumentProcessingCreate,
    DocumentProcessingRead,
    DocumentProcessingUpdate,
    FilePathsMapRequest,
    FilePathsMapResponse,
    IndexableStatusesRequest,
    IndexingRunCreate,
    IndexingRunRead,
    IndexingRunUpdate,
    MetadataFilterRequest,
    MetadataOptionsResponse,
    MemoryEmbeddingCreate,
    MemoryEmbeddingRead,
    MemoryEventCreate,
    MemoryEventRead,
    MemoryRecordCreate,
    MemoryRecordRead,
    MemoryRecordUpdate,
    QueryOptimizationRunCreate,
    QueryOptimizationRunRead,
    RetrievalRunCreate,
    RetrievalRunRead,
    RetrievalRunUpdate,
    RunIdResponse,
    SchemaOverview,
    ServiceErrorCreate,
    ServiceErrorRead,
    ServiceErrorUpdate,
    UploadedDocumentCreate,
    UploadedDocumentRead,
    UploadedDocumentUpdate,
    UserAuthRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from services.postgres_service.service import (
    build_uploaded_document_read,
    create_chat_message,
    create_chat_session,
    create_conversation_summary,
    create_document_processing,
    create_indexing_run,
    create_memory_embedding,
    create_memory_event,
    create_memory_record,
    create_query_optimization_run,
    create_retrieval_run,
    create_service_error,
    create_uploaded_document,
    create_user,
    delete_chat_session,
    delete_uploaded_document,
    get_chat_session,
    get_latest_conversation_summary,
    get_document_processing,
    get_indexing_run,
    get_latest_indexing_run_for_document,
    get_latest_document_processing,
    get_memory_embedding_by_memory_id,
    get_memory_record,
    get_query_optimization_run,
    get_retrieval_run,
    get_schema_overview,
    get_service_error,
    get_uploaded_document,
    get_uploaded_document_by_hash,
    get_uploaded_document_by_path,
    get_user,
    get_user_by_email,
    init_database,
    list_uploaded_documents,
    list_uploaded_documents_by_metadata_filters,
    list_storage_documents,
    build_uploaded_document_metadata_options,
    list_active_memory_records,
    list_chat_messages,
    list_indexable_document_ids,
    list_memory_events,
    list_session_query_optimization_runs,
    list_service_errors,
    list_user_chat_sessions,
    map_uploaded_documents_by_file_paths,
    purge_uploaded_document,
    update_chat_session,
    update_conversation_summary,
    update_indexing_run,
    update_memory_record,
    update_retrieval_run,
    update_service_error,
    update_document_processing,
    update_uploaded_document,
    update_user,
)

router = APIRouter(prefix="/db", tags=["postgres"])


@router.post("/init")
def init_tables() -> dict:
    init_database()
    return {"message": "Database tables initialized"}


@router.get("/schema", response_model=SchemaOverview)
def read_schema() -> SchemaOverview:
    return SchemaOverview(**get_schema_overview())


@router.post("/users", response_model=UserRead)
def create_user_endpoint(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    return create_user(db=db, payload=payload)


@router.get("/users/by-email", response_model=UserAuthRead)
def read_user_by_email(email: str = Query(...), db: Session = Depends(get_db)) -> UserAuthRead:
    user = get_user_by_email(db=db, email=email)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User with email '{email}' was not found.")
    return user


@router.get("/users/{user_id}", response_model=UserRead)
def read_user(user_id: str, db: Session = Depends(get_db)) -> UserRead:
    user = get_user(db=db, user_id=user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' was not found.")
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def patch_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)) -> UserRead:
    user = update_user(db=db, user_id=user_id, payload=payload)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' was not found.")
    return user


@router.post("/chat-sessions", response_model=ChatSessionRead)
def create_chat_session_endpoint(payload: ChatSessionCreate, db: Session = Depends(get_db)) -> ChatSessionRead:
    return create_chat_session(db=db, payload=payload)


@router.get("/chat-sessions/{session_id}", response_model=ChatSessionRead)
def read_chat_session(session_id: str, db: Session = Depends(get_db)) -> ChatSessionRead:
    session = get_chat_session(db=db, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Chat session '{session_id}' was not found.")
    return session


@router.get("/users/{user_id}/chat-sessions", response_model=list[ChatSessionRead])
def read_user_chat_sessions(user_id: str, db: Session = Depends(get_db)) -> list[ChatSessionRead]:
    return list_user_chat_sessions(db=db, user_id=user_id)


@router.patch("/chat-sessions/{session_id}", response_model=ChatSessionRead)
def patch_chat_session(
    session_id: str,
    payload: ChatSessionUpdate,
    db: Session = Depends(get_db),
) -> ChatSessionRead:
    session = update_chat_session(db=db, session_id=session_id, payload=payload)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Chat session '{session_id}' was not found.")
    return session


@router.delete("/chat-sessions/{session_id}", response_model=ChatSessionRead)
def delete_chat_session_endpoint(session_id: str, db: Session = Depends(get_db)) -> ChatSessionRead:
    session = delete_chat_session(db=db, session_id=session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Chat session '{session_id}' was not found.")
    return session


@router.post("/chat-messages", response_model=ChatMessageRead)
def create_chat_message_endpoint(payload: ChatMessageCreate, db: Session = Depends(get_db)) -> ChatMessageRead:
    return create_chat_message(db=db, payload=payload)


@router.get("/chat-sessions/{session_id}/messages", response_model=list[ChatMessageRead])
def read_chat_messages(session_id: str, db: Session = Depends(get_db)) -> list[ChatMessageRead]:
    return list_chat_messages(db=db, session_id=session_id)


@router.post("/conversation-summaries", response_model=ConversationSummaryRead)
def create_summary(payload: ConversationSummaryCreate, db: Session = Depends(get_db)) -> ConversationSummaryRead:
    return create_conversation_summary(db=db, payload=payload)


@router.get("/chat-sessions/{session_id}/summary", response_model=ConversationSummaryRead)
def read_latest_summary(session_id: str, db: Session = Depends(get_db)) -> ConversationSummaryRead:
    summary = get_latest_conversation_summary(db=db, session_id=session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"No summary found for session '{session_id}'.")
    return summary


@router.patch("/conversation-summaries/{summary_id}", response_model=ConversationSummaryRead)
def patch_summary(
    summary_id: str,
    payload: ConversationSummaryUpdate,
    db: Session = Depends(get_db),
) -> ConversationSummaryRead:
    summary = update_conversation_summary(db=db, summary_id=summary_id, payload=payload)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Summary '{summary_id}' was not found.")
    return summary


@router.post("/memory-records", response_model=MemoryRecordRead)
def create_memory_record_endpoint(payload: MemoryRecordCreate, db: Session = Depends(get_db)) -> MemoryRecordRead:
    return create_memory_record(db=db, payload=payload)


@router.get("/memory-records/{memory_id}", response_model=MemoryRecordRead)
def read_memory_record(memory_id: str, db: Session = Depends(get_db)) -> MemoryRecordRead:
    record = get_memory_record(db=db, memory_id=memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Memory record '{memory_id}' was not found.")
    return record


@router.get("/users/{user_id}/memory-records", response_model=list[MemoryRecordRead])
def read_active_memory_records(user_id: str, db: Session = Depends(get_db)) -> list[MemoryRecordRead]:
    return list_active_memory_records(db=db, user_id=user_id)


@router.patch("/memory-records/{memory_id}", response_model=MemoryRecordRead)
def patch_memory_record(
    memory_id: str,
    payload: MemoryRecordUpdate,
    db: Session = Depends(get_db),
) -> MemoryRecordRead:
    record = update_memory_record(db=db, memory_id=memory_id, payload=payload)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Memory record '{memory_id}' was not found.")
    return record


@router.post("/memory-embeddings", response_model=MemoryEmbeddingRead)
def create_memory_embedding_endpoint(
    payload: MemoryEmbeddingCreate,
    db: Session = Depends(get_db),
) -> MemoryEmbeddingRead:
    return create_memory_embedding(db=db, payload=payload)


@router.get("/memory-records/{memory_id}/embedding", response_model=MemoryEmbeddingRead)
def read_memory_embedding(memory_id: str, db: Session = Depends(get_db)) -> MemoryEmbeddingRead:
    embedding = get_memory_embedding_by_memory_id(db=db, memory_id=memory_id)
    if embedding is None:
        raise HTTPException(status_code=404, detail=f"No embedding found for memory '{memory_id}'.")
    return embedding


@router.post("/memory-events", response_model=MemoryEventRead)
def create_memory_event_endpoint(payload: MemoryEventCreate, db: Session = Depends(get_db)) -> MemoryEventRead:
    return create_memory_event(db=db, payload=payload)


@router.get("/memory-records/{memory_id}/events", response_model=list[MemoryEventRead])
def read_memory_events(memory_id: str, db: Session = Depends(get_db)) -> list[MemoryEventRead]:
    return list_memory_events(db=db, memory_id=memory_id)


@router.post("/query-optimization-runs", response_model=QueryOptimizationRunRead)
def create_query_optimization_run_endpoint(
    payload: QueryOptimizationRunCreate,
    db: Session = Depends(get_db),
) -> QueryOptimizationRunRead:
    return create_query_optimization_run(db=db, payload=payload)


@router.get("/query-optimization-runs/{query_run_id}", response_model=QueryOptimizationRunRead)
def read_query_optimization_run(
    query_run_id: str,
    db: Session = Depends(get_db),
) -> QueryOptimizationRunRead:
    run = get_query_optimization_run(db=db, query_run_id=query_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Query optimization run '{query_run_id}' was not found.")
    return run


@router.get("/chat-sessions/{session_id}/query-optimization-runs", response_model=list[QueryOptimizationRunRead])
def read_session_query_optimization_runs(
    session_id: str,
    db: Session = Depends(get_db),
) -> list[QueryOptimizationRunRead]:
    return list_session_query_optimization_runs(db=db, session_id=session_id)


@router.post("/uploaded-documents", response_model=UploadedDocumentRead)
def create_document(payload: UploadedDocumentCreate, db: Session = Depends(get_db)) -> UploadedDocumentRead:
    document = create_uploaded_document(db=db, payload=payload)
    return UploadedDocumentRead.model_validate(build_uploaded_document_read(document))


@router.get("/uploaded-documents", response_model=list[UploadedDocumentRead])
def read_uploaded_documents(limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db)) -> list[UploadedDocumentRead]:
    documents = list_uploaded_documents(db=db, limit=limit)
    return [UploadedDocumentRead.model_validate(build_uploaded_document_read(document)) for document in documents]


@router.get("/uploaded-documents/by-hash/{file_hash}", response_model=UploadedDocumentRead)
def read_document_by_hash(file_hash: str, db: Session = Depends(get_db)) -> UploadedDocumentRead:
    document = get_uploaded_document_by_hash(db=db, file_hash=file_hash)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document with hash '{file_hash}' was not found.")
    return UploadedDocumentRead.model_validate(build_uploaded_document_read(document))


@router.get("/uploaded-documents/by-path", response_model=UploadedDocumentRead)
def read_document_by_path(file_path: str = Query(...), db: Session = Depends(get_db)) -> UploadedDocumentRead:
    document = get_uploaded_document_by_path(db=db, file_path=file_path)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document with path '{file_path}' was not found.")
    return UploadedDocumentRead.model_validate(build_uploaded_document_read(document))


@router.get("/uploaded-documents/metadata-options", response_model=MetadataOptionsResponse)
def read_uploaded_document_metadata_options(db: Session = Depends(get_db)) -> MetadataOptionsResponse:
    return MetadataOptionsResponse(items=build_uploaded_document_metadata_options(db=db))


@router.post("/uploaded-documents/filter-by-metadata", response_model=list[UploadedDocumentRead])
def filter_uploaded_documents_by_metadata(
    payload: MetadataFilterRequest,
    db: Session = Depends(get_db),
) -> list[UploadedDocumentRead]:
    documents = list_uploaded_documents_by_metadata_filters(
        db=db,
        filters=payload.filters,
        limit=payload.limit,
    )
    return [UploadedDocumentRead.model_validate(build_uploaded_document_read(document)) for document in documents]


@router.get("/uploaded-documents/{document_id}", response_model=UploadedDocumentRead)
def read_document(document_id: str, db: Session = Depends(get_db)) -> UploadedDocumentRead:
    document = get_uploaded_document(db=db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' was not found.")
    return UploadedDocumentRead.model_validate(build_uploaded_document_read(document))


@router.patch("/uploaded-documents/{document_id}", response_model=UploadedDocumentRead)
def patch_document(
    document_id: str,
    payload: UploadedDocumentUpdate,
    db: Session = Depends(get_db),
) -> UploadedDocumentRead:
    document = update_uploaded_document(db=db, document_id=document_id, payload=payload)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' was not found.")
    return UploadedDocumentRead.model_validate(build_uploaded_document_read(document))


@router.delete("/uploaded-documents/{document_id}", response_model=UploadedDocumentRead)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> UploadedDocumentRead:
    document = delete_uploaded_document(db=db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' was not found.")
    return UploadedDocumentRead.model_validate(build_uploaded_document_read(document))


@router.delete("/uploaded-documents/{document_id}/purge")
def purge_document(document_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    result = purge_uploaded_document(db=db, document_id=document_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' was not found.")
    return result


@router.get("/documents/{document_id}", response_model=UploadedDocumentRead)
def read_document_public(document_id: str, db: Session = Depends(get_db)) -> UploadedDocumentRead:
    document = get_uploaded_document(db=db, document_id=document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' was not found.")
    return UploadedDocumentRead.model_validate(build_uploaded_document_read(document))


@router.patch("/documents/{document_id}/status", response_model=UploadedDocumentRead)
def patch_document_status(
    document_id: str,
    payload: DocumentStatusUpdate,
    db: Session = Depends(get_db),
) -> UploadedDocumentRead:
    document = update_uploaded_document(
        db=db,
        document_id=document_id,
        payload=UploadedDocumentUpdate(status=payload.status),
    )
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' was not found.")
    return UploadedDocumentRead.model_validate(build_uploaded_document_read(document))


@router.post("/documents/map-by-file-paths", response_model=FilePathsMapResponse)
def map_documents_by_paths(payload: FilePathsMapRequest, db: Session = Depends(get_db)) -> FilePathsMapResponse:
    return FilePathsMapResponse(items=map_uploaded_documents_by_file_paths(db=db, file_paths=payload.file_paths))


@router.get("/storage/documents", response_model=list[UploadedDocumentRead])
def read_storage_documents(
    storage_backend: str = Query(...),
    file_path_prefix: str | None = Query(default=None),
    exclude_status: str | None = Query(default="deleted"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[UploadedDocumentRead]:
    documents = list_storage_documents(
        db=db,
        storage_backend=storage_backend,
        file_path_prefix=file_path_prefix,
        exclude_status=exclude_status,
        limit=limit,
    )
    return [UploadedDocumentRead.model_validate(build_uploaded_document_read(document)) for document in documents]


@router.post("/document-processing", response_model=DocumentProcessingRead)
def create_processing(payload: DocumentProcessingCreate, db: Session = Depends(get_db)) -> DocumentProcessingRead:
    return create_document_processing(db=db, payload=payload)


@router.get("/document-processing/{processing_id}", response_model=DocumentProcessingRead)
def read_processing(processing_id: str, db: Session = Depends(get_db)) -> DocumentProcessingRead:
    processing = get_document_processing(db=db, processing_id=processing_id)
    if processing is None:
        raise HTTPException(status_code=404, detail=f"Processing '{processing_id}' was not found.")
    return processing


@router.patch("/document-processing/{processing_id}", response_model=DocumentProcessingRead)
def patch_processing(
    processing_id: str,
    payload: DocumentProcessingUpdate,
    db: Session = Depends(get_db),
) -> DocumentProcessingRead:
    processing = update_document_processing(db=db, processing_id=processing_id, payload=payload)
    if processing is None:
        raise HTTPException(status_code=404, detail=f"Processing '{processing_id}' was not found.")
    return processing


@router.get("/document-processing/latest/{document_id}", response_model=DocumentProcessingRead)
def read_latest_processing(document_id: str, db: Session = Depends(get_db)) -> DocumentProcessingRead:
    processing = get_latest_document_processing(db=db, document_id=document_id)
    if processing is None:
        raise HTTPException(status_code=404, detail=f"No processing rows were found for document '{document_id}'.")
    return processing


@router.post("/document-processing/list-indexable", response_model=list[DocumentIdsListItem])
def read_indexable_documents(payload: IndexableStatusesRequest, db: Session = Depends(get_db)) -> list[DocumentIdsListItem]:
    document_ids = list_indexable_document_ids(db=db, statuses=payload.statuses, limit=payload.limit)
    return [DocumentIdsListItem(document_id=document_id) for document_id in document_ids]


@router.post("/indexing-runs", response_model=RunIdResponse)
def create_indexing_run_endpoint(payload: IndexingRunCreate, db: Session = Depends(get_db)) -> RunIdResponse:
    run = create_indexing_run(db=db, payload=payload)
    return RunIdResponse(run_id=run.indexing_run_id)


@router.get("/indexing-runs/{run_id}", response_model=IndexingRunRead)
def read_indexing_run(run_id: str, db: Session = Depends(get_db)) -> IndexingRunRead:
    run = get_indexing_run(db=db, indexing_run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Indexing run '{run_id}' was not found.")
    return run


@router.get("/indexing-runs/latest/by-document/{document_id}", response_model=IndexingRunRead)
def read_latest_indexing_run_for_document(document_id: str, db: Session = Depends(get_db)) -> IndexingRunRead:
    run = get_latest_indexing_run_for_document(db=db, document_id=document_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No indexing run was found for document '{document_id}'.")
    return run


@router.patch("/indexing-runs/{run_id}", response_model=IndexingRunRead)
def patch_indexing_run(run_id: str, payload: IndexingRunUpdate, db: Session = Depends(get_db)) -> IndexingRunRead:
    run = update_indexing_run(db=db, indexing_run_id=run_id, payload=payload)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Indexing run '{run_id}' was not found.")
    return run


@router.post("/retrieval-runs", response_model=RunIdResponse)
def create_retrieval_run_endpoint(payload: RetrievalRunCreate, db: Session = Depends(get_db)) -> RunIdResponse:
    run = create_retrieval_run(db=db, payload=payload)
    return RunIdResponse(run_id=run.retrieval_run_id)


@router.get("/retrieval-runs/{run_id}", response_model=RetrievalRunRead)
def read_retrieval_run(run_id: str, db: Session = Depends(get_db)) -> RetrievalRunRead:
    run = get_retrieval_run(db=db, retrieval_run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Retrieval run '{run_id}' was not found.")
    return run


@router.patch("/retrieval-runs/{run_id}", response_model=RetrievalRunRead)
def patch_retrieval_run(run_id: str, payload: RetrievalRunUpdate, db: Session = Depends(get_db)) -> RetrievalRunRead:
    run = update_retrieval_run(db=db, retrieval_run_id=run_id, payload=payload)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Retrieval run '{run_id}' was not found.")
    return run


@router.post("/service-errors", response_model=ServiceErrorRead)
def create_service_error_endpoint(
    payload: ServiceErrorCreate,
    db: Session = Depends(get_db),
) -> ServiceErrorRead:
    return create_service_error(db=db, payload=payload)


@router.get("/service-errors/{error_id}", response_model=ServiceErrorRead)
def read_service_error(error_id: str, db: Session = Depends(get_db)) -> ServiceErrorRead:
    error = get_service_error(db=db, error_id=error_id)
    if error is None:
        raise HTTPException(status_code=404, detail=f"Service error '{error_id}' was not found.")
    return error


@router.patch("/service-errors/{error_id}", response_model=ServiceErrorRead)
def patch_service_error(
    error_id: str,
    payload: ServiceErrorUpdate,
    db: Session = Depends(get_db),
) -> ServiceErrorRead:
    error = update_service_error(db=db, error_id=error_id, payload=payload)
    if error is None:
        raise HTTPException(status_code=404, detail=f"Service error '{error_id}' was not found.")
    return error


@router.get("/service-errors", response_model=list[ServiceErrorRead])
def read_service_errors(
    service_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[ServiceErrorRead]:
    return list_service_errors(db=db, service_name=service_name, status=status, limit=limit)
