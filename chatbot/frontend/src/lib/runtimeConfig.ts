export const runtimeConfigStorageKey = "rag_runtime_config";

export type RuntimeConfigValues = Record<string, string>;

export type RuntimeConfigField = {
  key: string;
  label: string;
  placeholder?: string;
  type?: "text" | "password" | "url";
  multiline?: boolean;
};

export type RuntimeConfigSection = {
  key: string;
  title: string;
  description: string;
  fields: RuntimeConfigField[];
};

export const runtimeConfigSections: RuntimeConfigSection[] = [
  {
    key: "global",
    title: "Global / Shared",
    description: "Shared AI and infrastructure values that multiple services can reuse.",
    fields: [
      { key: "OPENAI_API_KEY", label: "LLM API key", type: "password" },
      { key: "OPENAI_BASE_URL", label: "Model gateway base URL", type: "url", placeholder: "https://..." },
      { key: "OPENAI_EMBEDDING_MODEL", label: "Embedding model name", placeholder: "text-embedding-3-large" },
      { key: "TIKTOKEN_MODEL_NAME", label: "Token counter model name", placeholder: "gpt-4o-mini" },
      { key: "POSTGRES_URL", label: "Postgres URL", placeholder: "postgresql+psycopg://user:pass@host:5432/db" },
      { key: "POSTGRES_SERVICE_URL", label: "Postgres service URL", type: "url", placeholder: "https://..." },
    ],
  },
  {
    key: "chatbot",
    title: "Chatbot",
    description: "Authentication, answer generation, retrieval, summary, and memory values for the chatbot app.",
    fields: [
      { key: "CHATBOT_ANSWER_BASE_URL", label: "Answer base URL", type: "url", placeholder: "https://..." },
      { key: "CHATBOT_ANSWER_MODEL", label: "Answer model", placeholder: "gpt-5.4" },
      { key: "CHATBOT_SUMMARY_MODEL", label: "Summary model", placeholder: "gpt-4o-mini" },
      { key: "CHATBOT_SUMMARY_TRIGGER_MESSAGES", label: "Summary trigger messages", placeholder: "12" },
      { key: "CHATBOT_SUMMARY_TRIGGER_TOKENS", label: "Summary trigger tokens", placeholder: "4000" },
      { key: "CHATBOT_SUMMARY_KEEP_MESSAGES", label: "Summary keep messages", placeholder: "4" },
      { key: "CHATBOT_SUMMARY_TRIM_TOKENS", label: "Summary trim tokens", placeholder: "4000" },
      { key: "CHATBOT_MEMORY_API_KEY", label: "Memory API key", type: "password" },
      { key: "CHATBOT_MEMORY_BASE_URL", label: "Memory base URL", type: "url", placeholder: "https://..." },
      { key: "CHATBOT_MEMORY_MODEL", label: "Memory model" },
      { key: "CHATBOT_MEMORY_TOP_K", label: "Memory top K", placeholder: "5" },
      { key: "CHATBOT_MEMORY_EXISTING_LIMIT", label: "Memory existing limit", placeholder: "8" },
      { key: "CHATBOT_MEMORY_LLM_MODEL", label: "Memory LLM model" },
      { key: "CHATBOT_MEMORY_EMBEDDING_MODEL", label: "Memory embedding model" },
      { key: "CHATBOT_MEMORY_EMBEDDING_DIM", label: "Memory embedding dimension", placeholder: "4096" },
      { key: "CHATBOT_QUERY_OPTIMIZER_API_KEY", label: "Query optimizer API key", type: "password" },
      { key: "CHATBOT_QUERY_OPTIMIZER_BASE_URL", label: "Query optimizer base URL", type: "url", placeholder: "https://..." },
      { key: "CHATBOT_QUERY_OPTIMIZER_MODEL", label: "Query optimizer model" },
      { key: "CHATBOT_RETRIEVAL_ENABLED", label: "Retrieval enabled", placeholder: "true / false" },
      { key: "CHATBOT_RETRIEVAL_SEARCH_TYPE", label: "Retrieval search type", placeholder: "hybrid" },
      { key: "CHATBOT_RETRIEVAL_TOP_K", label: "Retrieval top K", placeholder: "10" },
      { key: "LIGHTRAG_SERVICE_URL", label: "LightRAG service URL", type: "url", placeholder: "https://..." },
      { key: "LIGHTRAG_TIMEOUT_SECONDS", label: "LightRAG timeout seconds", placeholder: "180" },
    ],
  },
  {
    key: "upload",
    title: "Upload Service",
    description: "Values used when files are uploaded to the core engine before being forwarded to storage.",
    fields: [
      { key: "UPLOAD_SERVICE_URL", label: "Upload service URL", type: "url", placeholder: "https://..." },
    ],
  },
  {
    key: "storage",
    title: "Storage Service",
    description: "Provider and credential values used by the dedicated storage service.",
    fields: [
      { key: "STORAGE_SERVICE_URL", label: "Storage service URL", type: "url", placeholder: "https://..." },
      { key: "STORAGE_PROVIDER", label: "Storage provider", placeholder: "nextcloud / sharepoint / onedrive" },
      { key: "STORAGE_VERIFY_TLS", label: "Storage verify TLS", placeholder: "true / false" },
      { key: "NEXTCLOUD_BASE_URL", label: "Nextcloud base URL", type: "url", placeholder: "https://nextcloud" },
      { key: "NEXTCLOUD_USERNAME", label: "Nextcloud username" },
      { key: "NEXTCLOUD_PASSWORD", label: "Nextcloud password", type: "password" },
      { key: "NEXTCLOUD_ROOT_PATH", label: "Nextcloud root path", placeholder: "catalog / HR-Documents" },
      { key: "NEXTCLOUD_UPLOAD_FOLDER", label: "Nextcloud upload folder", placeholder: "raw-documents" },
      { key: "NEXTCLOUD_PROCESSED_FOLDER", label: "Nextcloud processed folder", placeholder: "processed-documents" },
      { key: "SHAREPOINT_POWER_AUTOMATE_URL", label: "SharePoint Power Automate URL", type: "url", placeholder: "https://..." },
      { key: "SHAREPOINT_FOLDER", label: "SharePoint root folder", placeholder: "/sites/.../Shared Documents/..." },
      { key: "SHAREPOINT_UPLOAD_FOLDER", label: "SharePoint upload folder", placeholder: "raw-documents" },
      { key: "SHAREPOINT_PROCESSED_FOLDER", label: "SharePoint processed folder", placeholder: "processed-documents" },
      { key: "ONEDRIVE_CLIENT_ID", label: "OneDrive client ID" },
      { key: "ONEDRIVE_CLIENT_SECRET", label: "OneDrive client secret", type: "password" },
      { key: "ONEDRIVE_AUTHORITY", label: "OneDrive authority", type: "url", placeholder: "https://login.microsoftonline.com/common" },
      { key: "ONEDRIVE_REFRESH_TOKEN", label: "OneDrive refresh token", type: "password" },
      { key: "ONEDRIVE_REFRESH_TOKEN_FILE", label: "OneDrive refresh token file", placeholder: "refresh_token.txt" },
      { key: "ONEDRIVE_ROOT_FOLDER", label: "OneDrive root folder", placeholder: "HR-Documents" },
      { key: "ONEDRIVE_UPLOAD_FOLDER", label: "OneDrive upload folder", placeholder: "raw-documents" },
      { key: "ONEDRIVE_PROCESSED_FOLDER", label: "OneDrive processed folder", placeholder: "processed-documents" },
    ],
  },
  {
    key: "docling",
    title: "Docling Service",
    description: "OCR and parsing configuration for document processing.",
    fields: [
      { key: "DOCLING_SERVICE_URL", label: "Docling service URL", type: "url", placeholder: "https://..." },
      { key: "PDF_OCR_ENGINE", label: "PDF OCR engine", placeholder: "easyocr" },
      { key: "EASYOCR_FRENCH_LANGUAGES", label: "EasyOCR French languages", placeholder: "fr,en" },
      { key: "EASYOCR_ARABIC_LANGUAGES", label: "EasyOCR Arabic languages", placeholder: "ar,en" },
      { key: "EASYOCR_USE_GPU", label: "EasyOCR use GPU", placeholder: "true / false" },
      { key: "DOCLING_LAYOUT_MODEL", label: "Docling layout model", placeholder: "docling_layout_v2" },
    ],
  },
  {
    key: "orchestration",
    title: "Orchestration Service",
    description: "Service-to-service endpoints and decision thresholds used by orchestration.",
    fields: [
      { key: "REQUEST_TIMEOUT_SECONDS", label: "Request timeout seconds", placeholder: "120" },
      { key: "CONFIDENCE_THRESHOLD", label: "Confidence threshold", placeholder: "0.95" },
      { key: "VLM_POLL_INTERVAL_SECONDS", label: "VLM poll interval seconds", placeholder: "2" },
      { key: "VLM_POLL_TIMEOUT_SECONDS", label: "VLM poll timeout seconds", placeholder: "90" },
      { key: "VLM_SERVICE_URL", label: "Project VLM service URL", type: "url", placeholder: "https://..." },
    ],
  },
  {
    key: "lightrag",
    title: "LightRAG Service",
    description: "Retrieval, vector store, graph, reranker, and indexing-related values.",
    fields: [
      { key: "QDRANT_URL", label: "Qdrant URL", type: "url", placeholder: "https://..." },
      { key: "QDRANT_API_KEY", label: "Qdrant API key", type: "password" },
      { key: "QDRANT_COLLECTION", label: "Qdrant collection" },
      { key: "NEO4J_URL", label: "Neo4j URL", placeholder: "bolt://..." },
      { key: "NEO4J_USER", label: "Neo4j user" },
      { key: "NEO4J_PASSWORD", label: "Neo4j password", type: "password" },
      { key: "LLM_MODEL_NAME", label: "LLM model name" },
      { key: "EMBEDDING_MODEL_NAME", label: "Embedding model name" },
      { key: "EMBEDDING_DIM", label: "Embedding dimension", placeholder: "4096" },
      { key: "RERANK_BASE_URL", label: "Rerank base URL", type: "url", placeholder: "https://..." },
      { key: "RERANK_BINDING_API_KEY", label: "Rerank API key", type: "password" },
      { key: "RERANK_MODEL_NAME", label: "Rerank model name" },
    ],
  },
  {
    key: "vlm",
    title: "VLM Service",
    description: "Values used by the VLM service itself when it calls the external OCR/model backend.",
    fields: [
      { key: "POSTGRES_SERVICE_URL", label: "VLM Postgres service URL", type: "url", placeholder: "http://127.0.0.1:8008" },
      { key: "STORAGE_SERVICE_URL", label: "VLM storage service URL", type: "url", placeholder: "http://127.0.0.1:8012" },
      { key: "VLM_BASE_URL", label: "External OCR/model base URL", type: "url", placeholder: "https://..." },
      { key: "VLM_OCR_API_KEY", label: "VLM OCR API key", type: "password" },
      { key: "VLM_MODEL_ID", label: "VLM model ID" },
      { key: "VLM_PROMPT", label: "VLM prompt", multiline: true, placeholder: "Return valid HTML only..." },
      { key: "VLM_PARSE_PROMPT", label: "VLM parse prompt", multiline: true, placeholder: "Optional parse prompt..." },
      { key: "VLM_REQUEST_TIMEOUT_SECONDS", label: "VLM request timeout seconds", placeholder: "300" },
      { key: "VLM_MAX_RETRIES", label: "VLM max retries", placeholder: "3" },
      { key: "VLM_RETRY_SLEEP_SECONDS", label: "VLM retry sleep seconds", placeholder: "120" },
      { key: "VLM_UNLOAD_MODELS_ON_CUDA_ERROR", label: "Unload models on CUDA error", placeholder: "true / false" },
    ],
  },
];

export function loadRuntimeConfig(): RuntimeConfigValues {
  if (typeof window === "undefined") {
    return {};
  }

  const raw = window.localStorage.getItem(runtimeConfigStorageKey);
  if (!raw) {
    return {};
  }

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return Object.fromEntries(
      Object.entries(parsed)
        .filter(([, value]) => typeof value === "string")
        .map(([key, value]) => [key, String(value)]),
    );
  } catch {
    return {};
  }
}

export function saveRuntimeConfig(values: RuntimeConfigValues) {
  if (typeof window === "undefined") {
    return;
  }

  const cleaned = Object.fromEntries(
    Object.entries(values)
      .map(([key, value]) => [key, value.trim()])
      .filter(([, value]) => value !== ""),
  );
  window.localStorage.setItem(runtimeConfigStorageKey, JSON.stringify(cleaned));
}

export function hasRuntimeConfig() {
  return Object.keys(loadRuntimeConfig()).length > 0;
}

export function clearRuntimeConfig() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(runtimeConfigStorageKey);
}

export function buildRuntimeConfigHeaders() {
  const values = loadRuntimeConfig();
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [
      `x-rag-${key.toLowerCase().replaceAll("_", "-")}`,
      value,
    ]),
  );
}
