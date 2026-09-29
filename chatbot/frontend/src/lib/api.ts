import type {
  AuthResponse,
  ChatHistoryMessage,
  ChatSession,
  DocumentDeleteResponse,
  DocumentMetadata,
  DocumentMetadataOptionsResponse,
  DocumentLibraryItem,
  DocumentStateResponse,
  IndexingResponse,
  PipelineResponse,
  RetrievalFilters,
  ServiceStatusResponse,
  StorageProvider,
  UploadedDocument,
  User,
} from "../types";
import { buildRuntimeConfigHeaders } from "./runtimeConfig";

const chatbotBaseUrl = import.meta.env.VITE_CHATBOT_API_URL || "/api/chatbot";
const orchestrationBaseUrl =
  import.meta.env.VITE_ORCHESTRATION_API_URL || "/api/orchestration";
const uploadServiceBaseUrl =
  import.meta.env.VITE_UPLOAD_SERVICE_API_URL || "/api/upload-service";

type RequestOptions = {
  token?: string;
  body?: unknown;
  formData?: FormData;
  params?: Record<string, string | number | boolean | undefined>;
};

type Base64FilePayload = {
  filename: string;
  content_type: string;
  size_bytes: number;
  base64_data: string;
  metadata_json?: DocumentMetadata;
};

async function readResponse(response: Response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function normalizeErrorDetail(detail: unknown): string {
  if (typeof detail !== "string") {
    return "Request failed.";
  }

  try {
    const nested = JSON.parse(detail);
    if (nested && typeof nested === "object" && "detail" in nested) {
      return String((nested as { detail: unknown }).detail);
    }
  } catch {
    // Keep original string when it is not JSON.
  }

  return detail;
}

async function requestJson<T>(
  baseUrl: string,
  path: string,
  method: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  const url = new URL(`${baseUrl}${path}`, window.location.origin);

  Object.assign(headers, buildRuntimeConfigHeaders());

  if (options.token) {
    headers.Authorization = `Bearer ${options.token}`;
  }

  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  if (options.params) {
    for (const [key, value] of Object.entries(options.params)) {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    }
  }

  const response = await fetch(url.toString(), {
    method,
    headers,
    body,
  });
  const payload = await readResponse(response);

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? normalizeErrorDetail((payload as { detail: unknown }).detail)
        : typeof payload === "string"
          ? payload
          : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }

  return payload as T;
}

export const apiConfig = {
  chatbotBaseUrl,
  orchestrationBaseUrl,
  uploadServiceBaseUrl,
};

export function login(email: string, password: string) {
  return requestJson<AuthResponse>(chatbotBaseUrl, "/auth/login", "POST", {
    body: { email, password },
  });
}

export function signup(name: string, email: string, password: string) {
  return requestJson<AuthResponse>(chatbotBaseUrl, "/auth/signup", "POST", {
    body: { name, email, password },
  });
}

export function getCurrentUser(token: string) {
  return requestJson<User>(chatbotBaseUrl, "/auth/me", "GET", { token });
}

export function sendChatMessage(
  token: string,
  sessionId: string | null,
  message: string,
  filters?: RetrievalFilters,
) {
  return requestJson<{ session_id: string; answer: string }>(chatbotBaseUrl, "/chat/message", "POST", {
    token,
    body: {
      session_id: sessionId,
      message,
      filters,
    },
  });
}

export function getChatSessions(token: string) {
  return requestJson<ChatSession[]>(chatbotBaseUrl, "/chat/sessions", "GET", { token });
}

export function getChatSessionMessages(token: string, sessionId: string) {
  return requestJson<ChatHistoryMessage[]>(
    chatbotBaseUrl,
    `/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
    "GET",
    { token },
  );
}

export function deleteChatSession(token: string, sessionId: string) {
  return requestJson<{ session_id: string }>(
    chatbotBaseUrl,
    `/chat/sessions/${encodeURIComponent(sessionId)}`,
    "DELETE",
    { token },
  );
}

export function getServiceStatus() {
  return requestJson<ServiceStatusResponse>(
    orchestrationBaseUrl,
    "/orchestration/status",
    "GET",
  );
}

export function initializeDatabase() {
  return requestJson<Record<string, unknown>>(
    orchestrationBaseUrl,
    "/orchestration/postgres/init",
    "POST",
  );
}

export function uploadDocument(
  file: File,
  provider: StorageProvider = "nextcloud",
  metadataJson?: DocumentMetadata,
) {
  if (shouldUseBase64Upload(file)) {
    return uploadDocumentAsBase64(file, provider, metadataJson);
  }
  const formData = new FormData();
  formData.append("file", file);
  if (metadataJson && Object.keys(metadataJson).length > 0) {
    formData.append("metadata_json", JSON.stringify(metadataJson));
  }
  return requestJson<UploadedDocument>(orchestrationBaseUrl, "/orchestration/upload", "POST", {
    formData,
    params: { provider },
  });
}

function shouldUseBase64Upload(file: File) {
  const normalizedName = file.name.toLowerCase();
  return normalizedName.endsWith(".pdf") || normalizedName.endsWith(".docx");
}

async function uploadDocumentAsBase64(
  file: File,
  provider: StorageProvider,
  metadataJson?: DocumentMetadata,
) {
  const payload = await fileToBase64Payload(file, metadataJson);
  return requestJson<UploadedDocument>(uploadServiceBaseUrl, "/documents/upload", "POST", {
    body: payload,
    params: { provider },
  });
}

async function fileToBase64Payload(
  file: File,
  metadataJson?: DocumentMetadata,
): Promise<Base64FilePayload> {
  const base64_data = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();

    reader.onerror = () => {
      reject(reader.error || new Error("Failed to read file"));
    };

    reader.onload = () => {
      const value = String(reader.result || "");
      const commaIndex = value.indexOf(",");
      resolve(commaIndex >= 0 ? value.slice(commaIndex + 1) : value);
    };

    reader.readAsDataURL(file);
  });

  return {
    filename: file.name,
    content_type: file.type || "application/octet-stream",
    size_bytes: file.size,
    base64_data,
    metadata_json: metadataJson,
  };
}

export function getDocumentMetadataOptions() {
  return requestJson<DocumentMetadataOptionsResponse>(
    orchestrationBaseUrl,
    "/orchestration/document-metadata/options",
    "GET",
  );
}

export function getDocuments(limit?: number) {
  return requestJson<DocumentLibraryItem[]>(
    orchestrationBaseUrl,
    "/orchestration/documents",
    "GET",
    limit === undefined
      ? {}
      : {
          params: { limit },
        },
  );
}

export function deleteDocumentEverywhere(documentId?: string, filePath?: string) {
  return requestJson<DocumentDeleteResponse>(
    orchestrationBaseUrl,
    "/orchestration/document/delete",
    "POST",
    {
      body: {
        document_id: documentId,
        file_path: filePath,
        delete_storage_file: true,
        delete_lightrag: true,
        delete_project_postgres: true,
        delete_llm_cache: false,
      },
    },
  );
}

export function getDocumentState(filePath: string) {
  return requestJson<DocumentStateResponse>(
    orchestrationBaseUrl,
    `/orchestration/document-state?file_path=${encodeURIComponent(filePath)}`,
    "GET",
  );
}

export function getDocumentStateByDocumentId(documentId: string) {
  return requestJson<DocumentStateResponse>(
    orchestrationBaseUrl,
    `/orchestration/document-state/by-document-id?document_id=${encodeURIComponent(documentId)}`,
    "GET",
  );
}

export function processDocument(filePath: string, languageHint: string) {
  return requestJson<PipelineResponse>(orchestrationBaseUrl, "/orchestration/process", "POST", {
    body: {
      file_path: filePath,
      language_hint: languageHint,
    },
  });
}

export function indexDocument(filePath: string) {
  return requestJson<IndexingResponse>(
    orchestrationBaseUrl,
    "/orchestration/lightrag/index-by-path",
    "POST",
    {
      body: {
        file_path: filePath,
      },
    },
  );
}
