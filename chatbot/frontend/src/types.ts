export type ViewKey = "chat" | "documents" | "settings";

export type StorageProvider = "nextcloud" | "onedrive" | "sharepoint";
export type DocumentMetadata = Record<string, string>;
export type RetrievalFilters = Record<string, string[]>;

export type User = {
  user_id: string;
  name: string;
  email: string;
};

export type AuthResponse = User & {
  access_token: string;
  token_type: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
};

export type ChatSession = {
  session_id: string;
  title?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ChatHistoryMessage = {
  message_id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string | null;
};

export type ServiceCard = {
  configured: boolean;
  reachable: boolean;
  url?: string | null;
  payload?: Record<string, unknown> | null;
  error?: string | null;
};

export type ServiceStatusResponse = {
  orchestration: ServiceCard;
  storage: ServiceCard;
  postgres: ServiceCard;
  upload: ServiceCard;
  docling: ServiceCard;
  vlm: ServiceCard;
  lightrag: ServiceCard;
};

export type UploadedDocument = {
  document_id?: string;
  file_path?: string;
  filename?: string;
  original_filename?: string;
  content_type?: string;
  file_size?: number;
  metadata_json?: DocumentMetadata;
  status?: string;
  [key: string]: unknown;
};

export type PipelineResponse = {
  uploaded_document?: UploadedDocument | null;
  docling_result?: Record<string, unknown> | null;
  latest_processing?: Record<string, unknown> | null;
  confidence_source?: string | null;
  confidence_value?: number | null;
  vlm_triggered: boolean;
  vlm_result?: Record<string, unknown> | null;
  final_markdown?: string | null;
  final_message: string;
};

export type IndexingResponse = {
  file_path?: string;
  document_id?: string;
  indexing_result?: {
    status?: string;
    run_id?: string;
    [key: string]: unknown;
  };
};

export type DocumentStateResponse = {
  uploaded_document?: UploadedDocument | null;
  latest_processing?: Record<string, unknown> | null;
  indexing_result?: {
    status?: string;
    document_id?: string;
    run_id?: string;
    [key: string]: unknown;
  } | null;
};

export type DocumentLibraryItem = {
  document_id?: string;
  file_path?: string;
  file_name?: string;
  storage_backend?: string | null;
  metadata_json?: DocumentMetadata;
  status?: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DocumentDeleteResponse = {
  status: "deleted" | "deleted_with_errors";
  document_id?: string;
  file_path?: string | null;
  storage_delete_result?: Record<string, unknown> | null;
  lightrag_delete_result?: Record<string, unknown> | null;
  postgres_purge_result?: Record<string, unknown> | null;
  errors?: Array<{ step: string; error: string }>;
  chatbot_visibility?: string;
};

export type DocumentMetadataOptionsResponse = {
  items: RetrievalFilters;
};
