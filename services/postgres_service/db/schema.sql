CREATE TABLE IF NOT EXISTS users (
    user_id character varying PRIMARY KEY,
    name character varying NOT NULL,
    email character varying NOT NULL UNIQUE,
    password_hash character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS uploaded_documents (
    document_id character varying PRIMARY KEY,
    storage_backend character varying NULL,
    file_name character varying NOT NULL,
    file_path character varying NOT NULL,
    mime_type character varying NULL,
    doc_type character varying NULL,
    file_hash character varying NULL,
    metadata_json jsonb NULL,
    status character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id character varying PRIMARY KEY,
    user_id character varying NOT NULL,
    title character varying NULL,
    status character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_chat_sessions_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id ON chat_sessions (user_id);

CREATE TABLE IF NOT EXISTS document_processing (
    processing_id character varying PRIMARY KEY,
    document_id character varying NOT NULL,
    processing_status character varying NOT NULL,
    parsed_at timestamp with time zone NULL,
    parser_name character varying NULL,
    parser_version character varying NULL,
    used_ocr boolean NULL,
    ocr_engine character varying NULL,
    ocr_confidence double precision NULL,
    layout_confidence double precision NULL,
    parse_confidence double precision NULL,
    table_confidence double precision NULL,
    mean_confidence double precision NULL,
    low_confidence double precision NULL,
    used_vlm boolean NULL,
    vlm_model character varying NULL,
    markdown_text text NULL,
    vlm_started_at timestamp with time zone NULL,
    vlm_processing_time double precision NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_document_processing_document
        FOREIGN KEY (document_id)
        REFERENCES uploaded_documents(document_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id character varying PRIMARY KEY,
    session_id character varying NOT NULL,
    role character varying NOT NULL,
    content text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_chat_messages_session
        FOREIGN KEY (session_id)
        REFERENCES chat_sessions(session_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id ON chat_messages (session_id);

CREATE TABLE IF NOT EXISTS indexing_runs (
    indexing_run_id character varying PRIMARY KEY,
    document_id character varying NOT NULL,
    pipeline_mode character varying NULL,
    status character varying NOT NULL,
    engine_name character varying NULL,
    engine_version character varying NULL,
    indexed_at timestamp with time zone NULL,
    finished_at timestamp with time zone NULL,
    error_message text NULL,
    output_summary text NULL,
    run_metadata jsonb NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_indexing_runs_document
        FOREIGN KEY (document_id)
        REFERENCES uploaded_documents(document_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    summary_id character varying PRIMARY KEY,
    session_id character varying NOT NULL,
    summary_text text NOT NULL,
    version integer NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_conversation_summaries_session
        FOREIGN KEY (session_id)
        REFERENCES chat_sessions(session_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_conversation_summaries_session_id ON conversation_summaries (session_id);

CREATE TABLE IF NOT EXISTS retrieval_runs (
    retrieval_run_id character varying PRIMARY KEY,
    document_id character varying NULL,
    mode character varying NULL,
    status character varying NOT NULL,
    query_text text NOT NULL,
    top_k integer NULL,
    filters jsonb NULL,
    latency_ms integer NULL,
    error_message text NULL,
    response_text text NULL,
    score double precision NULL,
    retrieved_at timestamp with time zone NULL,
    run_metadata jsonb NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_retrieval_runs_document
        FOREIGN KEY (document_id)
        REFERENCES uploaded_documents(document_id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS memory_records (
    memory_id character varying PRIMARY KEY,
    user_id character varying NOT NULL,
    session_id character varying NULL,
    source_message_id character varying NULL,
    memory_type character varying NOT NULL,
    confidence double precision NULL,
    is_active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_memory_records_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_memory_records_session
        FOREIGN KEY (session_id)
        REFERENCES chat_sessions(session_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_memory_records_source_message
        FOREIGN KEY (source_message_id)
        REFERENCES chat_messages(message_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_memory_records_user_id ON memory_records (user_id);
CREATE INDEX IF NOT EXISTS ix_memory_records_session_id ON memory_records (session_id);
CREATE INDEX IF NOT EXISTS ix_memory_records_source_message_id ON memory_records (source_message_id);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    embedding_id character varying PRIMARY KEY,
    memory_id character varying NOT NULL UNIQUE,
    qdrant_point_id character varying NOT NULL UNIQUE,
    embedding_model character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_memory_embeddings_memory
        FOREIGN KEY (memory_id)
        REFERENCES memory_records(memory_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_memory_embeddings_memory_id ON memory_embeddings (memory_id);

CREATE TABLE IF NOT EXISTS memory_events (
    event_id character varying PRIMARY KEY,
    memory_id character varying NOT NULL,
    event_type character varying NOT NULL,
    old_value text NULL,
    new_value text NULL,
    reason text NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_memory_events_memory
        FOREIGN KEY (memory_id)
        REFERENCES memory_records(memory_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_memory_events_memory_id ON memory_events (memory_id);

CREATE TABLE IF NOT EXISTS query_optimization_runs (
    query_run_id character varying PRIMARY KEY,
    session_id character varying NULL,
    user_id character varying NULL,
    original_query text NOT NULL,
    optimized_query text NOT NULL,
    route_type character varying NOT NULL,
    strategy character varying NULL,
    confidence double precision NULL,
    variants jsonb NULL,
    sub_questions jsonb NULL,
    used_llm boolean NOT NULL DEFAULT false,
    llm_model character varying NULL,
    reason text NULL,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT fk_query_optimization_runs_session
        FOREIGN KEY (session_id)
        REFERENCES chat_sessions(session_id)
        ON DELETE SET NULL,
    CONSTRAINT fk_query_optimization_runs_user
        FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS ix_query_optimization_runs_session_id ON query_optimization_runs (session_id);
CREATE INDEX IF NOT EXISTS ix_query_optimization_runs_user_id ON query_optimization_runs (user_id);
