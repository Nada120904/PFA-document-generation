from __future__ import annotations

import argparse
import getpass
import json
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG_DIR = ROOT / ".local"
DEFAULT_OUTPUT_PATH = LOCAL_CONFIG_DIR / "rag_runtime_profile.json"


@dataclass(frozen=True)
class PromptField:
    key: str
    label: str
    default: str = ""
    secret: bool = False
    required: bool = False
    help_text: str = ""


LOCAL_FIELDS: list[PromptField] = [
    PromptField("CHATBOT_API_URL", "Chatbot API URL", default="http://127.0.0.1:8015"),
    PromptField("ORCHESTRATION_API_URL", "Orchestration API URL", default="http://127.0.0.1:8010"),
    PromptField("LIGHTRAG_API_URL", "LightRAG API URL", default="http://127.0.0.1:8000"),
]


RUNTIME_FIELDS: list[PromptField] = [
    PromptField("STORAGE_URL", "Storage/WebDAV URL", default=""),
    PromptField("STORAGE_USER", "Storage/WebDAV user", default=""),
    PromptField("STORAGE_PASSWORD", "Storage/WebDAV password", default="", secret=True),
    PromptField("STORAGE_VERIFY_TLS", "Storage verify TLS (true/false)", default="true"),
    PromptField("QDRANT_URL", "Qdrant URL", required=True),
    PromptField("QDRANT_API_KEY", "Qdrant API key/token", default="", secret=True, required=True),
    PromptField("QDRANT_INSECURE_TLS", "Qdrant insecure TLS (true/false)", default="false"),
    PromptField("QDRANT_COLLECTION", "Chatbot memory Qdrant collection", default="rag_test2_chatbot_qdrant"),
    PromptField("QDRANT_COLLECTION_ENTITIES", "LightRAG entities collection", default="rag_test2_vectors_1"),
    PromptField("QDRANT_COLLECTION_RELATIONSHIPS", "LightRAG relationships collection", default="rag_test2_vectors_2"),
    PromptField("QDRANT_COLLECTION_CHUNKS", "LightRAG chunks collection", default="rag_test2_vectors_3"),
    PromptField("QDRANT_VECTOR_NAME_ENTITIES", "Entities vector name", default=""),
    PromptField("QDRANT_VECTOR_NAME_RELATIONSHIPS", "Relationships vector name", default=""),
    PromptField("QDRANT_VECTOR_NAME_CHUNKS", "Chunks vector name", default=""),
    PromptField("NEO4J_URL", "Neo4j URL", default=""),
    PromptField("NEO4J_USER", "Neo4j user", default="neo4j"),
    PromptField("NEO4J_PASSWORD", "Neo4j password", default="", secret=True),
    PromptField("NEO4J_DATABASE", "Neo4j database", default="neo4j"),
    PromptField("OPENAI_API_KEY", "Shared LLM/OpenAI-compatible API key", default="", secret=True),
    PromptField("OPENAI_BASE_URL", "Shared LLM/OpenAI-compatible base URL", default=""),
    PromptField("LLM_MODEL_NAME", "LightRAG LLM model name", default="qwen3.5:2b"),
    PromptField("TIKTOKEN_MODEL_NAME", "LightRAG tiktoken model name", default="gpt-4o-mini"),
    PromptField("EMBEDDING_MODEL_NAME", "LightRAG embedding model name", default="qwen3-embedding"),
    PromptField("EMBEDDING_DIM", "Embedding dimension", default="4096"),
    PromptField("RERANK_BINDING", "Rerank binding", default="huggingface"),
    PromptField("RERANK_MODEL_NAME", "Rerank model name", default="cross-encoder/ms-marco-MiniLM-L-6-v2"),
    PromptField("RERANK_BATCH_SIZE", "Rerank batch size", default="8"),
    PromptField("MIN_RERANK_SCORE", "Minimum rerank score", default="0.0"),
    PromptField("CHATBOT_QUERY_OPTIMIZER_MODEL", "Chatbot query optimizer model", default="gpt-4o-mini"),
    PromptField("CHATBOT_QUERY_OPTIMIZER_API_KEY", "Chatbot query optimizer API key", default="", secret=True),
    PromptField("CHATBOT_QUERY_OPTIMIZER_BASE_URL", "Chatbot query optimizer base URL", default=""),
    PromptField("CHATBOT_SUMMARY_MODEL", "Chatbot summary model", default="gpt-5.4"),
    PromptField("CHATBOT_ANSWER_MODEL", "Chatbot answer model", default="gpt-5.4"),
    PromptField("CHATBOT_ANSWER_BASE_URL", "Chatbot answer base URL", default=""),
    PromptField("CHATBOT_MEMORY_MODEL", "Chatbot memory model", default="ministral-3:8b"),
    PromptField("CHATBOT_MEMORY_LLM_MODEL", "Chatbot memory LLM model", default="ministral-3:8b"),
    PromptField("CHATBOT_MEMORY_EMBEDDING_MODEL", "Chatbot memory embedding model", default="qwen3-embedding:latest"),
    PromptField("CHATBOT_MEMORY_EMBEDDING_DIM", "Chatbot memory embedding dimension", default="4096"),
    PromptField("CHATBOT_MEMORY_API_KEY", "Chatbot memory API key", default="", secret=True),
    PromptField("CHATBOT_MEMORY_BASE_URL", "Chatbot memory base URL", default=""),
    PromptField("VLM_BASE_URL", "VLM/OCR base URL", default=""),
    PromptField("VLM_OCR_API_KEY", "VLM/OCR API key", default="", secret=True),
    PromptField("VLM_MODEL_ID", "VLM model id", default="datalab-to/chandra"),
    PromptField(
        "VLM_PROMPT",
        "VLM extraction prompt",
        default="Extract this document as clean structured HTML. Preserve sections, tables, labels, values, reading order, checkboxes, radio buttons, signatures, stamps, logos and icons. Use [x]/[ ] for checkboxes and (x)/( ) for radio buttons. For handwritten signatures write [Signature: handwritten signature present]. For stamps write [Stamp: readable text]. Do not summarize or invent. Return valid HTML only.",
    ),
    PromptField("VLM_REQUEST_TIMEOUT_SECONDS", "VLM request timeout seconds", default="300"),
]


CHATBOT_RUNTIME_KEYS: tuple[str, ...] = (
    "QDRANT_URL",
    "QDRANT_COLLECTION",
    "QDRANT_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "CHATBOT_QUERY_OPTIMIZER_MODEL",
    "CHATBOT_QUERY_OPTIMIZER_API_KEY",
    "CHATBOT_QUERY_OPTIMIZER_BASE_URL",
    "CHATBOT_SUMMARY_MODEL",
    "CHATBOT_ANSWER_MODEL",
    "CHATBOT_ANSWER_BASE_URL",
    "CHATBOT_MEMORY_MODEL",
    "CHATBOT_MEMORY_LLM_MODEL",
    "CHATBOT_MEMORY_EMBEDDING_MODEL",
    "CHATBOT_MEMORY_EMBEDDING_DIM",
    "CHATBOT_MEMORY_API_KEY",
    "CHATBOT_MEMORY_BASE_URL",
    "QDRANT_COLLECTION_ENTITIES",
    "QDRANT_COLLECTION_RELATIONSHIPS",
    "QDRANT_COLLECTION_CHUNKS",
    "QDRANT_VECTOR_NAME_ENTITIES",
    "QDRANT_VECTOR_NAME_RELATIONSHIPS",
    "QDRANT_VECTOR_NAME_CHUNKS",
    "QDRANT_INSECURE_TLS",
    "NEO4J_URL",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "LLM_MODEL_NAME",
    "TIKTOKEN_MODEL_NAME",
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_DIM",
    "RERANK_BINDING",
    "RERANK_MODEL_NAME",
    "RERANK_BATCH_SIZE",
    "MIN_RERANK_SCORE",
)

ORCHESTRATION_RUNTIME_KEYS: tuple[str, ...] = (
    "STORAGE_URL",
    "STORAGE_USER",
    "STORAGE_PASSWORD",
    "STORAGE_VERIFY_TLS",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_INSECURE_TLS",
    "QDRANT_COLLECTION_ENTITIES",
    "QDRANT_COLLECTION_RELATIONSHIPS",
    "QDRANT_COLLECTION_CHUNKS",
    "QDRANT_VECTOR_NAME_ENTITIES",
    "QDRANT_VECTOR_NAME_RELATIONSHIPS",
    "QDRANT_VECTOR_NAME_CHUNKS",
    "NEO4J_URL",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "LLM_MODEL_NAME",
    "TIKTOKEN_MODEL_NAME",
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_DIM",
    "RERANK_BINDING",
    "RERANK_MODEL_NAME",
    "RERANK_BATCH_SIZE",
    "MIN_RERANK_SCORE",
    "VLM_BASE_URL",
    "VLM_OCR_API_KEY",
    "VLM_MODEL_ID",
    "VLM_PROMPT",
    "VLM_REQUEST_TIMEOUT_SECONDS",
)

LIGHTRAG_RUNTIME_KEYS: tuple[str, ...] = (
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_INSECURE_TLS",
    "QDRANT_COLLECTION_ENTITIES",
    "QDRANT_COLLECTION_RELATIONSHIPS",
    "QDRANT_COLLECTION_CHUNKS",
    "QDRANT_VECTOR_NAME_ENTITIES",
    "QDRANT_VECTOR_NAME_RELATIONSHIPS",
    "QDRANT_VECTOR_NAME_CHUNKS",
    "NEO4J_URL",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "LLM_MODEL_NAME",
    "TIKTOKEN_MODEL_NAME",
    "EMBEDDING_MODEL_NAME",
    "EMBEDDING_DIM",
    "RERANK_BINDING",
    "RERANK_MODEL_NAME",
    "RERANK_BATCH_SIZE",
    "MIN_RERANK_SCORE",
)

VLM_RUNTIME_KEYS: tuple[str, ...] = (
    "STORAGE_USER",
    "STORAGE_PASSWORD",
    "STORAGE_VERIFY_TLS",
    "VLM_BASE_URL",
    "VLM_OCR_API_KEY",
    "VLM_MODEL_ID",
    "VLM_PROMPT",
    "VLM_REQUEST_TIMEOUT_SECONDS",
)


def _header_name(env_key: str) -> str:
    return f"x-rag-{env_key.lower().replace('_', '-')}"


def prompt_value(field: PromptField) -> str:
    while True:
        default_text = f" [{field.default}]" if field.default else ""
        if field.help_text:
            print(f"\n{field.label}: {field.help_text}")
        prompt = f"{field.label}{default_text}: "
        raw = getpass.getpass(prompt) if field.secret else input(prompt)
        value = raw.strip() if raw is not None else ""
        if not value:
            value = field.default
        if field.required and not value:
            print("This value is required.")
            continue
        return value


def collect_values() -> dict[str, str]:
    print("Local runtime setup for the shared RAG/chatbot server")
    print("This does not write server .env files.")
    print("It creates a local runtime profile that a caller project or future UI can use to send x-rag-* headers.\n")
    values: dict[str, str] = {}
    for field in [*LOCAL_FIELDS, *RUNTIME_FIELDS]:
        values[field.key] = prompt_value(field)
    return values


def _build_header_map(values: dict[str, str], keys: tuple[str, ...]) -> OrderedDict[str, str]:
    headers: OrderedDict[str, str] = OrderedDict()
    for key in keys:
        value = values.get(key, "").strip()
        if value:
            headers[_header_name(key)] = value
    return headers


def build_runtime_profile(values: dict[str, str]) -> OrderedDict[str, object]:
    chatbot_headers = _build_header_map(values, CHATBOT_RUNTIME_KEYS)
    orchestration_headers = _build_header_map(values, ORCHESTRATION_RUNTIME_KEYS)
    lightrag_headers = _build_header_map(values, LIGHTRAG_RUNTIME_KEYS)
    vlm_headers = _build_header_map(values, VLM_RUNTIME_KEYS)

    return OrderedDict(
        [
            ("schema_version", 1),
            (
                "description",
                (
                    "Local runtime profile for the shared RAG/chatbot core engine. "
                    "These values stay local and should be sent as x-rag-* headers per request."
                ),
            ),
            (
                "target_endpoints",
                OrderedDict(
                    [
                        ("chatbot_api_url", values["CHATBOT_API_URL"]),
                        ("orchestration_api_url", values["ORCHESTRATION_API_URL"]),
                        ("lightrag_api_url", values["LIGHTRAG_API_URL"]),
                    ]
                ),
            ),
            (
                "endpoint_presets",
                OrderedDict(
                    [
                        (
                            "chatbot",
                            OrderedDict(
                                [
                                    ("path", "/chat/message"),
                                    ("headers", chatbot_headers),
                                ]
                            ),
                        ),
                        (
                            "orchestration",
                            OrderedDict(
                                [
                                    ("path", "/orchestration/process"),
                                    ("headers", orchestration_headers),
                                ]
                            ),
                        ),
                        (
                            "lightrag",
                            OrderedDict(
                                [
                                    ("path", "/retrieval/text"),
                                    ("headers", lightrag_headers),
                                ]
                            ),
                        ),
                        (
                            "vlm",
                            OrderedDict(
                                [
                                    ("path", "/vlm/process-document/{processing_id}"),
                                    ("headers", vlm_headers),
                                ]
                            ),
                        ),
                    ]
                ),
            ),
        ]
    )


def write_profile(path: Path, profile: OrderedDict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    print(f"Wrote local runtime profile: {path}")


def print_summary(profile: OrderedDict[str, object]) -> None:
    endpoints = profile["target_endpoints"]
    presets = profile["endpoint_presets"]
    print("\nConfigured endpoints:")
    for name, url in endpoints.items():
        print(f"- {name}: {url}")
    print("\nHeader presets:")
    for name, preset in presets.items():
        headers = preset["headers"]
        print(f"- {name}: {len(headers)} runtime headers")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Collect local project credentials/config and build a runtime profile that sends "
            "x-rag-* headers to the shared RAG/chatbot server."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect values and print a summary without writing the local profile file.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Path to the local runtime profile JSON. Default: {DEFAULT_OUTPUT_PATH}",
    )
    args = parser.parse_args()

    values = collect_values()
    profile = build_runtime_profile(values)

    if args.dry_run:
        print_summary(profile)
        print("\nDry run complete. No local file was written.")
        return

    output_path = Path(args.output).resolve()
    write_profile(output_path, profile)
    print_summary(profile)
    print("\nSetup completed successfully.")
    print("Use this local profile from your caller project or future UI to attach runtime headers per request.")


if __name__ == "__main__":
    main()
