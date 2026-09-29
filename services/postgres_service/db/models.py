from __future__ import annotations

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    storage_backend: Mapped[str | None] = mapped_column(String, nullable=True)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String, nullable=True)
    doc_type: Mapped[str | None] = mapped_column(String, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    processing_runs: Mapped[list[DocumentProcessing]] = relationship(
        back_populates="document"
    )
    indexing_runs: Mapped[list[IndexingRun]] = relationship(
        back_populates="document"
    )
    retrieval_runs: Mapped[list[RetrievalRun]] = relationship(
        back_populates="document"
    )


class DocumentProcessing(Base):
    __tablename__ = "document_processing"

    processing_id: Mapped[str] = mapped_column(String, primary_key=True)

    document_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("uploaded_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )

    processing_status: Mapped[str] = mapped_column(String, nullable=False)

    parsed_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    parser_name: Mapped[str | None] = mapped_column(String, nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String, nullable=True)

    used_ocr: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ocr_engine: Mapped[str | None] = mapped_column(String, nullable=True)

    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    layout_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    parse_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    table_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    used_vlm: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    vlm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    markdown_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    vlm_started_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    vlm_processing_time: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    document: Mapped[UploadedDocument] = relationship(
        back_populates="processing_runs"
    )


class IndexingRun(Base):
    __tablename__ = "indexing_runs"

    indexing_run_id: Mapped[str] = mapped_column(String, primary_key=True)

    document_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("uploaded_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )

    pipeline_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    engine_name: Mapped[str | None] = mapped_column(String, nullable=True)
    engine_version: Mapped[str | None] = mapped_column(String, nullable=True)

    indexed_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    document: Mapped[UploadedDocument] = relationship(
        back_populates="indexing_runs"
    )


class RetrievalRun(Base):
    __tablename__ = "retrieval_runs"

    retrieval_run_id: Mapped[str] = mapped_column(String, primary_key=True)

    document_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("uploaded_documents.document_id", ondelete="SET NULL"),
        nullable=True,
    )

    mode: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)

    top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    retrieved_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    run_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    document: Mapped[UploadedDocument | None] = relationship(
        back_populates="retrieval_runs"
    )


class ServiceError(Base):
    __tablename__ = "service_errors"

    error_id: Mapped[str] = mapped_column(String, primary_key=True)
    service_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    operation_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("uploaded_documents.document_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    processing_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("document_processing.processing_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    indexing_run_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("indexing_runs.indexing_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    retrieval_run_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("retrieval_runs.retrieval_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    query_run_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("query_optimization_runs.query_run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("chat_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("chat_messages.message_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    resolved_at: Mapped[object | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"

    summary_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("chat_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class MemoryRecord(Base):
    __tablename__ = "memory_records"

    memory_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("chat_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_message_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("chat_messages.message_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    memory_type: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"

    embedding_id: Mapped[str] = mapped_column(String, primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("memory_records.memory_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    qdrant_point_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class MemoryEvent(Base):
    __tablename__ = "memory_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("memory_records.memory_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class QueryOptimizationRun(Base):
    __tablename__ = "query_optimization_runs"

    query_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("chat_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    original_query: Mapped[str] = mapped_column(Text, nullable=False)
    optimized_query: Mapped[str] = mapped_column(Text, nullable=False)
    route_type: Mapped[str] = mapped_column(String, nullable=False)
    strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    variants: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sub_questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    used_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
