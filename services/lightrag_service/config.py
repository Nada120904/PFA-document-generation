from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from services.runtime_config import apply_runtime_overrides

SERVICE_ENV_FILE = Path(__file__).with_name(".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(SERVICE_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "rag-service"
    environment: str = "development"
    log_level: str = "INFO"

    lightrag_working_dir: str = "data/lightrag"
    lightrag_chunk_size: int = 400
    lightrag_chunk_overlap_size: int = 80
    lightrag_enable_hierarchical_ingestion: bool = True
    lightrag_hierarchical_summary_max_chars: int = 900
    lightrag_enable_entity_dedup_postprocess: bool = True

    llm_model_name: str = "mistral"
    llm_timeout: int = 300
    llm_model_max_async: int = 1
    tiktoken_model_name: str = "gpt-4o-mini"
    embedding_model_name: str = "qwen3-embedding"
    embedding_dim: int = 4096
    embedding_timeout: int = 300
    embedding_func_max_async: int = 2

    postgres_url: str = "postgresql+psycopg://username:password@localhost:5432/rag_system"
    db_service_base_url: str = "http://127.0.0.1:8003"
    db_service_timeout: int = 30
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_insecure_tls: bool = False
    qdrant_collection_entities: str = ""
    qdrant_collection_relationships: str = ""
    qdrant_collection_chunks: str = ""
    qdrant_vector_name_entities: str = ""
    qdrant_vector_name_relationships: str = ""
    qdrant_vector_name_chunks: str = ""
    qdrant_upsert_max_payload_bytes: int = 16 * 1024 * 1024
    qdrant_upsert_max_points_per_batch: int = 128
    neo4j_url: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_insecure_tls: bool = False

    rerank_binding: str = ""
    rerank_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_batch_size: int = 8
    min_rerank_score: float = 0.0

    ragas_llm_model_name: str | None = None
    ragas_embedding_model_name: str | None = None


@lru_cache
def _get_base_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    return apply_runtime_overrides(_get_base_settings())
