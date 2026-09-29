"""Postgres service business logic."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from services.postgres_service.db.models import Base
from services.postgres_service.models import (
    ChatMessage,
    ChatSession,
    ConversationSummary,
    DocumentProcessing,
    IndexingRun,
    MemoryEmbedding,
    MemoryEvent,
    MemoryRecord,
    QueryOptimizationRun,
    RetrievalRun,
    ServiceError,
    UploadedDocument,
    User,
)
from services.postgres_service.config import get_settings
from services.postgres_service.db.postgres import get_engine
from services.postgres_service.schema import (
    ChatMessageCreate,
    ChatSessionCreate,
    ChatSessionUpdate,
    ConversationSummaryCreate,
    ConversationSummaryUpdate,
    DocumentProcessingCreate,
    DocumentProcessingUpdate,
    IndexingRunCreate,
    IndexingRunUpdate,
    MemoryEmbeddingCreate,
    MemoryEventCreate,
    MemoryRecordCreate,
    MemoryRecordUpdate,
    QueryOptimizationRunCreate,
    RetrievalRunCreate,
    RetrievalRunUpdate,
    ServiceErrorCreate,
    ServiceErrorUpdate,
    UploadedDocumentCreate,
    UploadedDocumentUpdate,
    UserCreate,
    UserUpdate,
)


def init_database() -> None:
    engine = get_engine(get_settings().postgres_url)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE uploaded_documents "
                "ADD COLUMN IF NOT EXISTS storage_backend character varying NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE uploaded_documents "
                "ADD COLUMN IF NOT EXISTS metadata_json jsonb NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE service_errors "
                "ADD COLUMN IF NOT EXISTS duration_ms integer NULL"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE service_errors "
                "ADD COLUMN IF NOT EXISTS error_context json NULL"
            )
        )


def normalize_metadata_json(metadata: dict | None) -> dict[str, str] | None:
    if not isinstance(metadata, dict):
        return None

    normalized: dict[str, str] = {}
    for key, value in metadata.items():
        key_text = str(key).strip().lower()
        value_text = str(value).strip()
        if not key_text or not value_text:
            continue
        normalized[key_text] = value_text

    return normalized or None


def create_uploaded_document(*, db: Session, payload: UploadedDocumentCreate) -> UploadedDocument:
    now = datetime.datetime.now(datetime.timezone.utc)
    document = UploadedDocument(
        document_id=payload.document_id,
        storage_backend=payload.storage_backend,
        file_name=payload.file_name,
        file_path=payload.file_path,
        mime_type=payload.mime_type,
        doc_type=payload.doc_type,
        file_hash=payload.file_hash,
        metadata_json=normalize_metadata_json(payload.metadata_json),
        status=payload.status,
        created_at=now,
        updated_at=now,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def get_uploaded_document(*, db: Session, document_id: str) -> UploadedDocument | None:
    return db.get(UploadedDocument, document_id)


def get_uploaded_document_by_hash(*, db: Session, file_hash: str) -> UploadedDocument | None:
    return db.scalar(select(UploadedDocument).where(UploadedDocument.file_hash == file_hash))


def get_uploaded_document_by_path(*, db: Session, file_path: str) -> UploadedDocument | None:
    return db.scalar(select(UploadedDocument).where(UploadedDocument.file_path == file_path))


def list_uploaded_documents(*, db: Session, limit: int = 200) -> list[UploadedDocument]:
    query = (
        select(UploadedDocument)
        .order_by(UploadedDocument.updated_at.desc(), UploadedDocument.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(query).all())


def list_storage_documents(
    *,
    db: Session,
    storage_backend: str,
    file_path_prefix: str | None = None,
    exclude_status: str | None = "deleted",
    limit: int = 200,
) -> list[UploadedDocument]:
    query = select(UploadedDocument).where(UploadedDocument.storage_backend == storage_backend)

    if file_path_prefix:
        query = query.where(UploadedDocument.file_path.startswith(file_path_prefix))

    if exclude_status:
        query = query.where(UploadedDocument.status != exclude_status)

    query = query.order_by(UploadedDocument.created_at.desc()).limit(limit)
    return list(db.scalars(query).all())


def list_uploaded_documents_by_metadata_filters(
    *,
    db: Session,
    filters: dict[str, list[str]],
    exclude_status: str | None = "deleted",
    limit: int = 1000,
) -> list[UploadedDocument]:
    normalized_filters = {
        str(key).strip().lower(): [str(value).strip() for value in values if str(value).strip()]
        for key, values in filters.items()
        if str(key).strip() and isinstance(values, list)
    }

    query = select(UploadedDocument)
    if exclude_status:
        query = query.where(UploadedDocument.status != exclude_status)

    metadata_conditions = []
    for key, values in normalized_filters.items():
        if not values:
            continue
        metadata_conditions.append(
            UploadedDocument.metadata_json[key].as_string().in_(values)
        )

    if metadata_conditions:
        query = query.where(or_(*metadata_conditions))

    query = query.order_by(UploadedDocument.updated_at.desc()).limit(limit)
    return list(db.scalars(query).all())


def build_uploaded_document_metadata_options(*, db: Session) -> dict[str, list[str]]:
    rows = db.scalars(
        select(UploadedDocument).where(UploadedDocument.metadata_json.is_not(None))
    ).all()
    items: dict[str, set[str]] = {}
    for row in rows:
        if not isinstance(row.metadata_json, dict):
            continue
        for key, value in row.metadata_json.items():
            key_text = str(key).strip().lower()
            value_text = str(value).strip()
            if not key_text or not value_text:
                continue
            items.setdefault(key_text, set()).add(value_text)
    return {key: sorted(values) for key, values in sorted(items.items())}


def map_uploaded_documents_by_file_paths(*, db: Session, file_paths: list[str]) -> dict[str, str]:
    if not file_paths:
        return {}

    rows = db.scalars(
        select(UploadedDocument).where(UploadedDocument.file_path.in_(file_paths))
    ).all()

    return {row.file_path: row.document_id for row in rows}


def update_uploaded_document(
    *,
    db: Session,
    document_id: str,
    payload: UploadedDocumentUpdate,
) -> UploadedDocument | None:
    document = db.get(UploadedDocument, document_id)
    if document is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    if "metadata_json" in update_data:
        update_data["metadata_json"] = normalize_metadata_json(update_data["metadata_json"])
    for field, value in update_data.items():
        setattr(document, field, value)

    document.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def delete_uploaded_document(*, db: Session, document_id: str) -> UploadedDocument | None:
    document = db.get(UploadedDocument, document_id)
    if document is None:
        return None

    db.delete(document)
    db.commit()
    return document


def purge_uploaded_document(*, db: Session, document_id: str) -> dict | None:
    """
    Hard-delete a document and explicitly clean related rows.
    This is safer when DB-level ON DELETE rules are not applied uniformly.
    """
    document = db.get(UploadedDocument, document_id)
    if document is None:
        return None

    document_read = build_uploaded_document_read(document)

    deleted_processing = (
        db.query(DocumentProcessing)
        .filter(DocumentProcessing.document_id == document_id)
        .delete(synchronize_session=False)
    )
    deleted_indexing_runs = (
        db.query(IndexingRun)
        .filter(IndexingRun.document_id == document_id)
        .delete(synchronize_session=False)
    )
    detached_retrieval_runs = (
        db.query(RetrievalRun)
        .filter(RetrievalRun.document_id == document_id)
        .update({RetrievalRun.document_id: None}, synchronize_session=False)
    )

    db.delete(document)
    db.commit()

    return {
        "document": document_read,
        "deleted_document_processing": int(deleted_processing),
        "deleted_indexing_runs": int(deleted_indexing_runs),
        "detached_retrieval_runs": int(detached_retrieval_runs),
    }


def build_uploaded_document_read(document: UploadedDocument) -> dict:
    return {
        "document_id": document.document_id,
        "storage_backend": document.storage_backend,
        "file_name": document.file_name,
        "file_path": document.file_path,
        "mime_type": document.mime_type,
        "doc_type": document.doc_type,
        "file_hash": document.file_hash,
        "metadata_json": document.metadata_json,
        "status": document.status,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def create_document_processing(
    *,
    db: Session,
    payload: DocumentProcessingCreate,
) -> DocumentProcessing:
    now = datetime.datetime.now(datetime.timezone.utc)

    processing = DocumentProcessing(
        processing_id=payload.processing_id,
        document_id=payload.document_id,
        processing_status=payload.processing_status,

        parsed_at=payload.parsed_at,
        parser_name=payload.parser_name,
        parser_version=payload.parser_version,

        used_ocr=payload.used_ocr,
        ocr_engine=payload.ocr_engine,
        ocr_confidence=payload.ocr_confidence,
        layout_confidence=payload.layout_confidence,
        parse_confidence=payload.parse_confidence,
        table_confidence=payload.table_confidence,
        mean_confidence=payload.mean_confidence,
        low_confidence=payload.low_confidence,

        used_vlm=payload.used_vlm,
        vlm_model=payload.vlm_model,
        markdown_text=payload.markdown_text,
        vlm_started_at=payload.vlm_started_at,
        vlm_processing_time=payload.vlm_processing_time,

        created_at=now,
        updated_at=now,
    )

    db.add(processing)
    db.commit()
    db.refresh(processing)
    return processing


def get_document_processing(*, db: Session, processing_id: str) -> DocumentProcessing | None:
    return db.get(DocumentProcessing, processing_id)


def get_latest_document_processing(*, db: Session, document_id: str) -> DocumentProcessing | None:
    return db.scalar(
        select(DocumentProcessing)
        .where(DocumentProcessing.document_id == document_id)
        .order_by(
            DocumentProcessing.updated_at.desc(),
            DocumentProcessing.created_at.desc(),
        )
        .limit(1)
    )


def list_indexable_document_ids(
    *,
    db: Session,
    statuses: list[str],
    limit: int,
) -> list[str]:
    if not statuses:
        return []

    latest_subquery = (
        select(
            DocumentProcessing.document_id.label("document_id"),
            func.max(DocumentProcessing.updated_at).label("latest_updated_at"),
        )
        .group_by(DocumentProcessing.document_id)
        .subquery()
    )

    rows = db.execute(
        select(DocumentProcessing.document_id)
        .join(
            latest_subquery,
            (DocumentProcessing.document_id == latest_subquery.c.document_id)
            & (DocumentProcessing.updated_at == latest_subquery.c.latest_updated_at),
        )
        .where(DocumentProcessing.processing_status.in_(statuses))
        .limit(limit)
    ).all()

    return [row[0] for row in rows]


def update_document_processing(
    *,
    db: Session,
    processing_id: str,
    payload: DocumentProcessingUpdate,
) -> DocumentProcessing | None:
    processing = db.get(DocumentProcessing, processing_id)
    if processing is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(processing, field, value)

    processing.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(processing)
    db.commit()
    db.refresh(processing)
    return processing


def create_indexing_run(*, db: Session, payload: IndexingRunCreate) -> IndexingRun:
    now = datetime.datetime.now(datetime.timezone.utc)

    run = IndexingRun(
        indexing_run_id=str(uuid.uuid4()),
        document_id=payload.document_id,
        pipeline_mode=payload.pipeline_mode,
        status=payload.status,
        created_at=now,
        updated_at=now,
    )

    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_indexing_run(*, db: Session, indexing_run_id: str) -> IndexingRun | None:
    return db.get(IndexingRun, indexing_run_id)


def get_latest_indexing_run_for_document(*, db: Session, document_id: str) -> IndexingRun | None:
    return (
        db.query(IndexingRun)
        .filter(IndexingRun.document_id == document_id)
        .order_by(IndexingRun.updated_at.desc(), IndexingRun.created_at.desc())
        .first()
    )


def update_indexing_run(
    *,
    db: Session,
    indexing_run_id: str,
    payload: IndexingRunUpdate,
) -> IndexingRun | None:
    run = db.get(IndexingRun, indexing_run_id)
    if run is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(run, field, value)

    run.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_retrieval_run(*, db: Session, payload: RetrievalRunCreate) -> RetrievalRun:
    now = datetime.datetime.now(datetime.timezone.utc)

    run = RetrievalRun(
        retrieval_run_id=str(uuid.uuid4()),
        document_id=payload.document_id,
        mode=payload.mode,
        status=payload.status,
        query_text=payload.query_text,
        top_k=payload.top_k,
        filters=payload.filters,
        created_at=now,
        updated_at=now,
    )

    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_retrieval_run(*, db: Session, retrieval_run_id: str) -> RetrievalRun | None:
    return db.get(RetrievalRun, retrieval_run_id)


def update_retrieval_run(
    *,
    db: Session,
    retrieval_run_id: str,
    payload: RetrievalRunUpdate,
) -> RetrievalRun | None:
    run = db.get(RetrievalRun, retrieval_run_id)
    if run is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(run, field, value)

    run.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_service_error(*, db: Session, payload: ServiceErrorCreate) -> ServiceError:
    now = datetime.datetime.now(datetime.timezone.utc)
    error = ServiceError(
        error_id=str(uuid.uuid4()),
        service_name=payload.service_name,
        operation_name=payload.operation_name,
        status=payload.status,
        error_message=payload.error_message,
        error_context=payload.error_context,
        retry_count=payload.retry_count,
        duration_ms=payload.duration_ms,
        document_id=payload.document_id,
        processing_id=payload.processing_id,
        indexing_run_id=payload.indexing_run_id,
        retrieval_run_id=payload.retrieval_run_id,
        query_run_id=payload.query_run_id,
        session_id=payload.session_id,
        message_id=payload.message_id,
        user_id=payload.user_id,
        resolved_at=payload.resolved_at,
        created_at=now,
        updated_at=now,
    )
    db.add(error)
    db.commit()
    db.refresh(error)
    return error


def get_service_error(*, db: Session, error_id: str) -> ServiceError | None:
    return db.get(ServiceError, error_id)


def list_service_errors(
    *,
    db: Session,
    service_name: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[ServiceError]:
    query = select(ServiceError)
    if service_name:
        query = query.where(ServiceError.service_name == service_name)
    if status:
        query = query.where(ServiceError.status == status)
    return list(
        db.scalars(
            query.order_by(ServiceError.created_at.desc()).limit(limit)
        ).all()
    )


def update_service_error(
    *,
    db: Session,
    error_id: str,
    payload: ServiceErrorUpdate,
) -> ServiceError | None:
    error = db.get(ServiceError, error_id)
    if error is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(error, field, value)

    error.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(error)
    db.commit()
    db.refresh(error)
    return error


def create_user(*, db: Session, payload: UserCreate) -> User:
    now = datetime.datetime.now(datetime.timezone.utc)
    user = User(
        user_id=payload.user_id,
        name=payload.name,
        email=payload.email,
        password_hash=payload.password_hash,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user(*, db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(*, db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def update_user(*, db: Session, user_id: str, payload: UserUpdate) -> User | None:
    user = db.get(User, user_id)
    if user is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    user.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_chat_session(*, db: Session, payload: ChatSessionCreate) -> ChatSession:
    now = datetime.datetime.now(datetime.timezone.utc)
    session = ChatSession(
        session_id=payload.session_id,
        user_id=payload.user_id,
        title=payload.title,
        status=payload.status,
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_chat_session(*, db: Session, session_id: str) -> ChatSession | None:
    return db.get(ChatSession, session_id)


def list_user_chat_sessions(*, db: Session, user_id: str) -> list[ChatSession]:
    return db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc())
    ).all()


def update_chat_session(
    *,
    db: Session,
    session_id: str,
    payload: ChatSessionUpdate,
) -> ChatSession | None:
    session = db.get(ChatSession, session_id)
    if session is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)

    session.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def delete_chat_session(*, db: Session, session_id: str) -> ChatSession | None:
    session = db.get(ChatSession, session_id)
    if session is None:
        return None

    db.delete(session)
    db.commit()
    return session


def create_chat_message(*, db: Session, payload: ChatMessageCreate) -> ChatMessage:
    message = ChatMessage(
        message_id=payload.message_id,
        session_id=payload.session_id,
        role=payload.role,
        content=payload.content,
    )
    db.add(message)
    session = db.get(ChatSession, payload.session_id)
    if session is not None:
        session.updated_at = datetime.datetime.now(datetime.timezone.utc)
        db.add(session)
    db.commit()
    db.refresh(message)
    return message


def list_chat_messages(*, db: Session, session_id: str) -> list[ChatMessage]:
    return db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    ).all()


def create_conversation_summary(
    *,
    db: Session,
    payload: ConversationSummaryCreate,
) -> ConversationSummary:
    summary = ConversationSummary(
        summary_id=payload.summary_id,
        session_id=payload.session_id,
        summary_text=payload.summary_text,
        version=payload.version,
    )
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def get_latest_conversation_summary(*, db: Session, session_id: str) -> ConversationSummary | None:
    return db.scalar(
        select(ConversationSummary)
        .where(ConversationSummary.session_id == session_id)
        .order_by(ConversationSummary.version.desc(), ConversationSummary.updated_at.desc())
        .limit(1)
    )


def update_conversation_summary(
    *,
    db: Session,
    summary_id: str,
    payload: ConversationSummaryUpdate,
) -> ConversationSummary | None:
    summary = db.get(ConversationSummary, summary_id)
    if summary is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(summary, field, value)

    summary.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(summary)
    db.commit()
    db.refresh(summary)
    return summary


def create_memory_record(*, db: Session, payload: MemoryRecordCreate) -> MemoryRecord:
    now = datetime.datetime.now(datetime.timezone.utc)
    record = MemoryRecord(
        memory_id=payload.memory_id,
        user_id=payload.user_id,
        session_id=payload.session_id,
        source_message_id=payload.source_message_id,
        memory_type=payload.memory_type,
        confidence=payload.confidence,
        is_active=payload.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_memory_record(*, db: Session, memory_id: str) -> MemoryRecord | None:
    return db.get(MemoryRecord, memory_id)


def list_active_memory_records(*, db: Session, user_id: str) -> list[MemoryRecord]:
    return db.scalars(
        select(MemoryRecord)
        .where(MemoryRecord.user_id == user_id, MemoryRecord.is_active.is_(True))
        .order_by(MemoryRecord.updated_at.desc(), MemoryRecord.created_at.desc())
    ).all()


def update_memory_record(
    *,
    db: Session,
    memory_id: str,
    payload: MemoryRecordUpdate,
) -> MemoryRecord | None:
    record = db.get(MemoryRecord, memory_id)
    if record is None:
        return None

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    record.updated_at = datetime.datetime.now(datetime.timezone.utc)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def create_memory_embedding(*, db: Session, payload: MemoryEmbeddingCreate) -> MemoryEmbedding:
    embedding = MemoryEmbedding(
        embedding_id=payload.embedding_id,
        memory_id=payload.memory_id,
        qdrant_point_id=payload.qdrant_point_id,
        embedding_model=payload.embedding_model,
    )
    db.add(embedding)
    db.commit()
    db.refresh(embedding)
    return embedding


def get_memory_embedding_by_memory_id(*, db: Session, memory_id: str) -> MemoryEmbedding | None:
    return db.scalar(select(MemoryEmbedding).where(MemoryEmbedding.memory_id == memory_id))


def create_memory_event(*, db: Session, payload: MemoryEventCreate) -> MemoryEvent:
    event = MemoryEvent(
        event_id=payload.event_id,
        memory_id=payload.memory_id,
        event_type=payload.event_type,
        old_value=payload.old_value,
        new_value=payload.new_value,
        reason=payload.reason,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_memory_events(*, db: Session, memory_id: str) -> list[MemoryEvent]:
    return db.scalars(
        select(MemoryEvent)
        .where(MemoryEvent.memory_id == memory_id)
        .order_by(MemoryEvent.created_at.desc())
    ).all()


def create_query_optimization_run(
    *,
    db: Session,
    payload: QueryOptimizationRunCreate,
) -> QueryOptimizationRun:
    run = QueryOptimizationRun(**payload.model_dump())
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_query_optimization_run(*, db: Session, query_run_id: str) -> QueryOptimizationRun | None:
    return db.get(QueryOptimizationRun, query_run_id)


def list_session_query_optimization_runs(
    *,
    db: Session,
    session_id: str,
) -> list[QueryOptimizationRun]:
    return db.scalars(
        select(QueryOptimizationRun)
        .where(QueryOptimizationRun.session_id == session_id)
        .order_by(QueryOptimizationRun.created_at.desc())
    ).all()


def get_schema_overview() -> dict:
    return {
        "tables": [
            {
                "name": "users",
                "purpose": "Chatbot user identities used for authentication and ownership of sessions/memory.",
                "primary_key": "user_id",
                "columns": [
                    "user_id",
                    "name",
                    "email",
                    "password_hash",
                    "created_at",
                    "updated_at",
                ],
            },
            {
                "name": "chat_sessions",
                "purpose": "Chatbot conversation threads belonging to authenticated users.",
                "primary_key": "session_id",
                "columns": [
                    "session_id",
                    "user_id",
                    "title",
                    "status",
                    "created_at",
                    "updated_at",
                ],
            },
            {
                "name": "chat_messages",
                "purpose": "Raw per-session chatbot messages.",
                "primary_key": "message_id",
                "columns": [
                    "message_id",
                    "session_id",
                    "role",
                    "content",
                    "created_at",
                ],
            },
            {
                "name": "conversation_summaries",
                "purpose": "Session summaries used to keep chat context compact.",
                "primary_key": "summary_id",
                "columns": [
                    "summary_id",
                    "session_id",
                    "summary_text",
                    "version",
                    "updated_at",
                ],
            },
            {
                "name": "memory_records",
                "purpose": "Long-term memory metadata for chatbot users.",
                "primary_key": "memory_id",
                "columns": [
                    "memory_id",
                    "user_id",
                    "session_id",
                    "source_message_id",
                    "memory_type",
                    "confidence",
                    "is_active",
                    "created_at",
                    "updated_at",
                ],
            },
            {
                "name": "memory_embeddings",
                "purpose": "Mapping between memory records and Qdrant embedding points.",
                "primary_key": "embedding_id",
                "columns": [
                    "embedding_id",
                    "memory_id",
                    "qdrant_point_id",
                    "embedding_model",
                    "created_at",
                ],
            },
            {
                "name": "memory_events",
                "purpose": "Audit trail for memory changes.",
                "primary_key": "event_id",
                "columns": [
                    "event_id",
                    "memory_id",
                    "event_type",
                    "old_value",
                    "new_value",
                    "reason",
                    "created_at",
                ],
            },
            {
                "name": "query_optimization_runs",
                "purpose": "Trace each chatbot query optimization decision before retrieval.",
                "primary_key": "query_run_id",
                "columns": [
                    "query_run_id",
                    "session_id",
                    "user_id",
                    "original_query",
                    "optimized_query",
                    "route_type",
                    "strategy",
                    "confidence",
                    "variants",
                    "sub_questions",
                    "used_llm",
                    "llm_model",
                    "reason",
                    "created_at",
                ],
            },
            {
                "name": "uploaded_documents",
                "purpose": "Basic uploaded-file tracking owned by the upload service.",
                "primary_key": "document_id",
                "columns": [
                    "document_id",
                    "storage_backend",
                    "file_name",
                    "file_path",
                    "mime_type",
                    "doc_type",
                    "file_hash",
                    "status",
                    "created_at",
                    "updated_at",
                ],
            },
            {
                "name": "document_processing",
                "purpose": (
                    "Document OCR/parsing confidence tracking and optional VLM "
                    "post-processing result storage."
                ),
                "primary_key": "processing_id",
                "columns": [
                    "processing_id",
                    "document_id",
                    "processing_status",
                    "parsed_at",
                    "parser_name",
                    "parser_version",
                    "used_ocr",
                    "ocr_engine",
                    "ocr_confidence",
                    "layout_confidence",
                    "parse_confidence",
                    "table_confidence",
                    "mean_confidence",
                    "low_confidence",
                    "used_vlm",
                    "vlm_model",
                    "markdown_text",
                    "vlm_started_at",
                    "vlm_processing_time",
                    "created_at",
                    "updated_at",
                ],
            },
            {
                "name": "indexing_runs",
                "purpose": "Indexing execution tracking owned by the indexing service.",
                "primary_key": "indexing_run_id",
                "columns": [
                    "indexing_run_id",
                    "document_id",
                    "pipeline_mode",
                    "status",
                    "engine_name",
                    "engine_version",
                    "indexed_at",
                    "finished_at",
                    "error_message",
                    "output_summary",
                    "run_metadata",
                    "created_at",
                    "updated_at",
                ],
            },
            {
                "name": "retrieval_runs",
                "purpose": "Retrieval execution tracking owned by the retrieval service.",
                "primary_key": "retrieval_run_id",
                "columns": [
                    "retrieval_run_id",
                    "document_id",
                    "mode",
                    "status",
                    "query_text",
                    "top_k",
                    "filters",
                    "latency_ms",
                    "error_message",
                    "response_text",
                    "score",
                    "retrieved_at",
                    "run_metadata",
                    "created_at",
                    "updated_at",
                ],
            },
            {
                "name": "service_errors",
                "purpose": (
                    "Unified error tracking for all services and workflows, with optional "
                    "links to the relevant run/document/session records."
                ),
                "primary_key": "error_id",
                "columns": [
                    "error_id",
                    "service_name",
                    "operation_name",
                    "status",
                    "error_message",
                    "error_context",
                    "retry_count",
                    "duration_ms",
                    "document_id",
                    "processing_id",
                    "indexing_run_id",
                    "retrieval_run_id",
                    "query_run_id",
                    "session_id",
                    "message_id",
                    "user_id",
                    "created_at",
                    "resolved_at",
                    "updated_at",
                ],
            },
        ],
        "relations": [
            {
                "from_table": "chat_sessions",
                "from_column": "user_id",
                "to_table": "users",
                "to_column": "user_id",
                "on_delete": "CASCADE",
            },
            {
                "from_table": "chat_messages",
                "from_column": "session_id",
                "to_table": "chat_sessions",
                "to_column": "session_id",
                "on_delete": "CASCADE",
            },
            {
                "from_table": "conversation_summaries",
                "from_column": "session_id",
                "to_table": "chat_sessions",
                "to_column": "session_id",
                "on_delete": "CASCADE",
            },
            {
                "from_table": "memory_records",
                "from_column": "user_id",
                "to_table": "users",
                "to_column": "user_id",
                "on_delete": "CASCADE",
            },
            {
                "from_table": "memory_records",
                "from_column": "session_id",
                "to_table": "chat_sessions",
                "to_column": "session_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "memory_records",
                "from_column": "source_message_id",
                "to_table": "chat_messages",
                "to_column": "message_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "memory_embeddings",
                "from_column": "memory_id",
                "to_table": "memory_records",
                "to_column": "memory_id",
                "on_delete": "CASCADE",
            },
            {
                "from_table": "memory_events",
                "from_column": "memory_id",
                "to_table": "memory_records",
                "to_column": "memory_id",
                "on_delete": "CASCADE",
            },
            {
                "from_table": "query_optimization_runs",
                "from_column": "session_id",
                "to_table": "chat_sessions",
                "to_column": "session_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "query_optimization_runs",
                "from_column": "user_id",
                "to_table": "users",
                "to_column": "user_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "document_processing",
                "from_column": "document_id",
                "to_table": "uploaded_documents",
                "to_column": "document_id",
                "on_delete": "CASCADE",
            },
            {
                "from_table": "indexing_runs",
                "from_column": "document_id",
                "to_table": "uploaded_documents",
                "to_column": "document_id",
                "on_delete": "CASCADE",
            },
            {
                "from_table": "retrieval_runs",
                "from_column": "document_id",
                "to_table": "uploaded_documents",
                "to_column": "document_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "service_errors",
                "from_column": "document_id",
                "to_table": "uploaded_documents",
                "to_column": "document_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "service_errors",
                "from_column": "processing_id",
                "to_table": "document_processing",
                "to_column": "processing_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "service_errors",
                "from_column": "indexing_run_id",
                "to_table": "indexing_runs",
                "to_column": "indexing_run_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "service_errors",
                "from_column": "retrieval_run_id",
                "to_table": "retrieval_runs",
                "to_column": "retrieval_run_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "service_errors",
                "from_column": "query_run_id",
                "to_table": "query_optimization_runs",
                "to_column": "query_run_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "service_errors",
                "from_column": "session_id",
                "to_table": "chat_sessions",
                "to_column": "session_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "service_errors",
                "from_column": "message_id",
                "to_table": "chat_messages",
                "to_column": "message_id",
                "on_delete": "SET NULL",
            },
            {
                "from_table": "service_errors",
                "from_column": "user_id",
                "to_table": "users",
                "to_column": "user_id",
                "on_delete": "SET NULL",
            },
        ],
    }
