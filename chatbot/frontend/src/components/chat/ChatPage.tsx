import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Clock3,
  CircleX,
  ExternalLink,
  FileUp,
  Filter,
  Loader2,
  Play,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import {
  getDocumentState,
  getDocumentStateByDocumentId,
  getDocumentMetadataOptions,
  indexDocument,
  processDocument,
  sendChatMessage,
  uploadDocument,
} from "../../lib/api";
import type {
  ChatMessage,
  DocumentMetadata,
  DocumentMetadataOptionsResponse,
  DocumentStateResponse,
  IndexingResponse,
  PipelineResponse,
  RetrievalFilters,
  StorageProvider,
  UploadedDocument,
} from "../../types";
import { StatusBadge } from "../shared/StatusBadge";

type ChatPageProps = {
  token: string;
  messages: ChatMessage[];
  sessionId: string | null;
  refreshRevision: number;
  documentState: {
    uploadedDocument: UploadedDocument | null;
    pipelineResult: PipelineResponse | null;
    indexingResult: IndexingResponse | null;
  };
  onMessagesChange: (messages: ChatMessage[]) => void;
  onSessionChange: (sessionId: string) => void;
  onNewChat: () => void;
  onUploadedDocument: (document: UploadedDocument | null) => void;
  onPipelineResult: (result: PipelineResponse | null) => void;
  onIndexingResult: (result: IndexingResponse | null) => void;
};

const DOWNLOAD_LINK_PATTERN = /\[Download (PDF|DOCX|TXT|CSV)\]\((\/api\/chatbot\/generate\/download\/[a-f0-9]+\.\w+)\)/;

type GeneratedPreview = { filename: string; format: string; text: string; rows?: string[][] };

function GeneratedFileCard({ format, url }: { format: string; url: string }) {
  const [preview, setPreview] = useState<GeneratedPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const filename = url.split("/").pop() || "download";
  const openUrl = url.replace("/download/", "/open/");

  useEffect(() => {
    if (!isOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [isOpen]);

  async function togglePreview() {
    if (preview) {
      setPreview(null);
      return;
    }
    setLoading(true);
    setPreviewError("");
    try {
      const response = await fetch(url.replace("/download/", "/preview/"));
      if (!response.ok) throw new Error(`Preview unavailable (${response.status})`);
      setPreview((await response.json()) as GeneratedPreview);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "Preview unavailable");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="generated-file-block">
      <div className="generated-file-card">
        <div className="generated-file-icon">{format}</div>
        <div className="generated-file-info">
          <strong>{filename}</strong>
          <span>Generated from uploaded files</span>
        </div>
        <button type="button" className="generated-file-preview-button" onClick={togglePreview} disabled={loading}>
          {loading ? "Loading…" : preview ? "Hide preview" : "Preview"}
        </button>
        <button type="button" className="generated-file-preview-button generated-file-open-button" onClick={() => setIsOpen(true)}>
          <ExternalLink size={14} aria-hidden="true" /> Open file
        </button>
        <a className="primary-button generated-file-download" href={url} download>
          <Send size={14} aria-hidden="true" style={{ transform: "rotate(-90deg)" }} />
          Download
        </a>
      </div>
      {previewError && <p className="generated-file-preview-error" role="alert">{previewError}</p>}
      {preview && (
        <div className="generated-file-preview" aria-label={`${format} preview`}>
          <strong>File preview · {format}</strong>
          {preview.rows ? (
            <div className="generated-file-table-wrap"><table><tbody>
              {preview.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>{row.map((cell, cellIndex) => rowIndex === 0
                  ? <th key={cellIndex}>{cell}</th> : <td key={cellIndex}>{cell}</td>)}</tr>
              ))}
            </tbody></table></div>
          ) : <pre>{preview.text}</pre>}
        </div>
      )}
      {isOpen && createPortal(
        <div className="generated-viewer-overlay" onMouseDown={() => setIsOpen(false)}>
          <section className="generated-viewer-dialog" role="dialog" aria-modal="true" aria-label={`Opened ${format} file`} onMouseDown={(event) => event.stopPropagation()}>
            <div className="generated-viewer-header">
              <div><strong>Opened {format} file</strong><span>{filename}</span></div>
              <button type="button" onClick={() => setIsOpen(false)} aria-label="Close file viewer"><CircleX size={22} /></button>
            </div>
            <iframe src={openUrl} title={`${format} file contents`} />
          </section>
        </div>, document.body,
      )}
    </div>
  );
}

function renderMessageContent(content: string) {
  const match = content.match(DOWNLOAD_LINK_PATTERN);
  if (!match) {
    return <ReactMarkdown>{content}</ReactMarkdown>;
  }

  const [fullMatch, format, url] = match;
  const textBefore = content.slice(0, match.index).trim();
  return (
    <>
      {textBefore && <ReactMarkdown>{textBefore}</ReactMarkdown>}
      <GeneratedFileCard format={format} url={url} />
    </>
  );
}

type DocumentStep = "idle" | "uploading" | "processing" | "indexing" | "done" | "error";
type StepVisualStatus = "idle" | "active" | "done" | "error";
type StepAction = "upload" | "process" | "index" | null;
type QueueAction =
  | "new"
  | "done"
  | "process"
  | "index"
  | "retry-upload"
  | "retry-process"
  | "retry-index";
type QueueItemState = "waiting" | "checking" | "running" | "done" | "error";
type DocumentMessageMode = "fresh" | "existing-indexed" | "resume-from-uploaded" | "resume-from-processed";

type QueueItem = {
  id: string;
  file: File;
  fileName: string;
  storageProvider: StorageProvider;
  state: QueueItemState;
  action: QueueAction;
  label: string;
  message: string;
  metadataPairs: MetadataPair[];
  documentId?: string;
  filePath?: string;
};

type MetadataPair = {
  id: string;
  key: string;
  value: string;
};

type FilterGroup = {
  id: string;
  label: string;
  originalKeys: string[];
  values: string[];
};

const DOCUMENT_POLL_INTERVAL_MS = 5000;
const DOCUMENT_POLL_TIMEOUT_MS = 15 * 60 * 1000;

function isErrorStatus(value: unknown) {
  const normalized = String(value || "").toLowerCase();
  return normalized === "failed" || normalized === "error";
}

function normalizeUploadedStatus(value: unknown) {
  return String(value || "").toLowerCase();
}

function getSuccessMessage(mode: DocumentMessageMode | null) {
  switch (mode) {
    case "existing-indexed":
      return "This document already exists and is already uploaded, processed, and indexed.";
    case "resume-from-uploaded":
      return "Document already uploaded. Processing and indexing completed successfully.";
    case "resume-from-processed":
      return "Document already uploaded and processed. Indexing completed successfully.";
    case "fresh":
    default:
      return "Document uploaded, processed, and indexed successfully.";
  }
}

function buildMetadataFromPairs(pairs: MetadataPair[]): DocumentMetadata {
  return pairs.reduce<DocumentMetadata>((accumulator, pair) => {
    const key = pair.key.trim();
    const value = pair.value.trim();
    if (key && value) {
      accumulator[key] = value;
    }
    return accumulator;
  }, {});
}

function formatFilterGroupLabel(key: string) {
  const trimmed = key.trim();
  if (!trimmed) return "Metadata";
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

function buildFilterGroups(options: RetrievalFilters): FilterGroup[] {
  const groups = new Map<string, { label: string; originalKeys: Set<string>; values: Set<string> }>();

  for (const [key, values] of Object.entries(options)) {
    const normalizedKey = key.trim().toLowerCase();
    if (!normalizedKey) continue;
    const existing = groups.get(normalizedKey) ?? {
      label: formatFilterGroupLabel(normalizedKey),
      originalKeys: new Set<string>(),
      values: new Set<string>(),
    };
    existing.originalKeys.add(key);
    for (const value of values) {
      const trimmedValue = value.trim();
      if (trimmedValue) {
        existing.values.add(trimmedValue);
      }
    }
    groups.set(normalizedKey, existing);
  }

  return Array.from(groups.entries())
    .map(([id, group]) => ({
      id,
      label: group.label,
      originalKeys: Array.from(group.originalKeys),
      values: Array.from(group.values).sort((left, right) => left.localeCompare(right)),
    }))
    .sort((left, right) => left.label.localeCompare(right.label));
}

function expandFiltersForRequest(selectedFilters: RetrievalFilters, filterGroups: FilterGroup[]): RetrievalFilters {
  const expanded: RetrievalFilters = {};

  for (const group of filterGroups) {
    const selectedValues = selectedFilters[group.id] || [];
    if (selectedValues.length === 0) continue;
    for (const originalKey of group.originalKeys) {
      expanded[originalKey] = [...selectedValues];
    }
  }

  return expanded;
}

function deriveQueueActionFromState(state: DocumentStateResponse): {
  action: QueueAction;
  label: string;
  message: string;
} {
  const uploadedStatus = normalizeUploadedStatus(state.uploaded_document?.status);
  const processingStatus = normalizeUploadedStatus(state.latest_processing?.processing_status);
  const indexingStatus = normalizeUploadedStatus(state.indexing_result?.status);

  if (uploadedStatus === "indexed" || indexingStatus === "indexed") {
    return {
      action: "done",
      label: "Already indexed",
      message: "This document already exists and is already uploaded, processed, and indexed.",
    };
  }

  if (isErrorStatus(indexingStatus)) {
    return {
      action: "retry-index",
      label: "Retry indexing",
      message: String(state.indexing_result?.error || state.indexing_result?.error_message || "Indexing failed."),
    };
  }

  if (
    processingStatus === "parsed" ||
    uploadedStatus === "parsed" ||
    Boolean(state.latest_processing?.markdown_text)
  ) {
    return {
      action: "index",
      label: "Continue indexing",
      message: "Document already uploaded and parsed. Continue with indexing.",
    };
  }

  if (isErrorStatus(processingStatus)) {
    return {
      action: "retry-process",
      label: "Retry processing",
      message: String(state.latest_processing?.error_message || "Processing failed."),
    };
  }

  if (state.uploaded_document?.file_path || uploadedStatus === "uploaded") {
    return {
      action: "process",
      label: "Continue processing",
      message: "Document already uploaded. Continue with processing.",
    };
  }

  if (isErrorStatus(uploadedStatus)) {
    return {
      action: "retry-upload",
      label: "Retry upload",
      message: "Upload failed.",
    };
  }

  return {
    action: "new",
    label: "New",
    message: "Document will start from upload.",
  };
}

export function ChatPage({
  token,
  messages,
  sessionId,
  refreshRevision,
  documentState,
  onMessagesChange,
  onSessionChange,
  onNewChat,
  onUploadedDocument,
  onPipelineResult,
  onIndexingResult,
}: ChatPageProps) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [documentStep, setDocumentStep] = useState<DocumentStep>("idle");
  const [documentMessage, setDocumentMessage] = useState("");
  const [pendingAction, setPendingAction] = useState<StepAction>(null);
  const [storageProvider, setStorageProvider] = useState<StorageProvider>("nextcloud");
  const [documentMessageMode, setDocumentMessageMode] = useState<DocumentMessageMode | null>(null);
  const [attemptedFileName, setAttemptedFileName] = useState("");
  const [queueItems, setQueueItems] = useState<QueueItem[]>([]);
  const [activeQueueItemId, setActiveQueueItemId] = useState<string | null>(null);
  const [isQueueRunning, setIsQueueRunning] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [metadataOptions, setMetadataOptions] = useState<RetrievalFilters>({});
  const [selectedFilters, setSelectedFilters] = useState<RetrievalFilters>({});
  const [expandedFilterGroups, setExpandedFilterGroups] = useState<Record<string, boolean>>({});
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const queueItemsRef = useRef<QueueItem[]>([]);

  const currentFilePath = useMemo(
    () =>
      documentState.uploadedDocument?.file_path ||
      documentState.pipelineResult?.uploaded_document?.file_path ||
      documentState.indexingResult?.file_path ||
      "",
    [documentState],
  );

  const currentDocumentId = useMemo(
    () =>
      documentState.uploadedDocument?.document_id ||
      documentState.pipelineResult?.uploaded_document?.document_id ||
      documentState.indexingResult?.document_id ||
      documentState.indexingResult?.indexing_result?.document_id ||
      "",
    [documentState],
  );

  const indexingMatchesCurrentDocument = useMemo(() => {
    const indexingDocumentId = String(
      documentState.indexingResult?.document_id || documentState.indexingResult?.indexing_result?.document_id || "",
    ).trim();
    const indexingFilePath = String(documentState.indexingResult?.file_path || "").trim();

    if (!documentState.indexingResult) {
      return false;
    }

    if (currentDocumentId && indexingDocumentId) {
      return currentDocumentId === indexingDocumentId;
    }

    if (currentFilePath && indexingFilePath) {
      return currentFilePath === indexingFilePath;
    }

    return false;
  }, [currentDocumentId, currentFilePath, documentState.indexingResult]);

  const resolvedIndexingStatus = indexingMatchesCurrentDocument
    ? String(documentState.indexingResult?.indexing_result?.status || "").toLowerCase()
    : "";
  const hasActualIndexingRun = Boolean(
    documentState.indexingResult?.indexing_result?.run_id || documentState.indexingResult?.indexing_result?.indexed_at,
  );

  const processingStatus = String(documentState.pipelineResult?.latest_processing?.processing_status || "").toLowerCase();
  const uploadedStatus = String(documentState.uploadedDocument?.status || "").toLowerCase();

  const uploadDone = Boolean(currentFilePath);
  const processFailed = documentStep !== "uploading" && isErrorStatus(processingStatus);
  const rawProcessDone =
    !processFailed &&
    (processingStatus === "parsed" ||
      uploadedStatus === "parsed" ||
      uploadedStatus === "indexed" ||
      Boolean(documentState.pipelineResult?.final_markdown));
  const processDone = documentStep === "uploading" ? false : rawProcessDone;
  const indexingFailed = documentStep !== "uploading" && documentStep !== "processing" && hasActualIndexingRun && isErrorStatus(resolvedIndexingStatus);
  const rawIndexingDone =
    !processFailed && !indexingFailed && (resolvedIndexingStatus === "indexed" || uploadedStatus === "indexed");
  const indexingDone = documentStep === "uploading" || documentStep === "processing" ? false : rawIndexingDone;

  const knowledgeState = useMemo(() => {
    if (documentStep === "uploading") return "Uploading";
    if (documentStep === "processing") return "Processing";
    if (documentStep === "indexing") return "Indexing";
    if (indexingFailed || processFailed || uploadedStatus === "error") return "Error";
    if (indexingDone) return "Indexed";
    if (processDone) return "Processed";
    if (uploadDone) return "Uploaded";
    return "No document";
  }, [documentStep, indexingDone, indexingFailed, processDone, processFailed, uploadDone, uploadedStatus]);

  const uploadRowStatus: StepVisualStatus =
    documentStep === "uploading" ? "active" : uploadDone ? "done" : documentStep === "error" && !uploadDone ? "error" : "idle";
  const processRowStatus: StepVisualStatus =
    documentStep === "processing" ? "active" : processFailed ? "error" : processDone ? "done" : "idle";
  const indexRowStatus: StepVisualStatus =
    documentStep === "indexing" ? "active" : processFailed ? "idle" : indexingFailed ? "error" : indexingDone ? "done" : "idle";

  const canUploadNewDocument = documentStep !== "uploading" && documentStep !== "processing" && documentStep !== "indexing";

  const queueCompletedCount = queueItems.filter((item) => item.state === "done").length;
  const queueErrorCount = queueItems.filter((item) => item.state === "error").length;
  const queueRunningCount = queueItems.filter((item) => item.state === "running" || item.state === "checking").length;
  const hasActiveFilters = Object.keys(selectedFilters).length > 0;
  const filterGroups = useMemo(() => buildFilterGroups(metadataOptions), [metadataOptions]);

  useEffect(() => {
    queueItemsRef.current = queueItems;
  }, [queueItems]);

  useEffect(() => {
    void reloadMetadataOptions();
  }, []);

  async function reloadMetadataOptions() {
    try {
      const response: DocumentMetadataOptionsResponse = await getDocumentMetadataOptions();
      setMetadataOptions(response.items || {});
    } catch {
      setMetadataOptions({});
    }
  }

  useEffect(() => {
    if (documentStep === "uploading" || documentStep === "processing" || documentStep === "indexing") {
      return;
    }

    if (!uploadDone) {
      if (documentStep === "error") {
        return;
      }
      setDocumentStep("idle");
      setPendingAction(null);
      setDocumentMessage("");
      setDocumentMessageMode(null);
      setAttemptedFileName("");
      return;
    }

    if (processFailed) {
      setDocumentStep("error");
      setPendingAction(null);
      setDocumentMessage(
        String(documentState.pipelineResult?.latest_processing?.error_message || "Processing failed. Retry processing."),
      );
      return;
    }

    if (indexingFailed) {
      setDocumentStep("error");
      setPendingAction(null);
      setDocumentMessage(
        String(documentState.indexingResult?.indexing_result?.error_message || "Indexing failed. Retry indexing."),
      );
      return;
    }

    if (indexingDone) {
      setDocumentStep("done");
      setPendingAction(null);
      setDocumentMessage(
        getSuccessMessage(documentMessageMode),
      );
      return;
    }

    if (uploadDone && processDone) {
      setDocumentStep("idle");
      setPendingAction(null);
      setDocumentMessage("Document already uploaded and parsed. Continue with indexing.");
      return;
    }

    if (uploadDone) {
      setDocumentStep("idle");
      setPendingAction(null);
      setDocumentMessage("Document already uploaded. Continue with processing.");
    }
  }, [
    documentStep,
    documentMessageMode,
    documentState.indexingResult?.indexing_result?.error_message,
    documentState.pipelineResult?.latest_processing?.error_message,
    indexingDone,
    indexingFailed,
    processDone,
    processFailed,
    uploadDone,
  ]);

  useEffect(() => {
    setShowFilters(false);
    setSelectedFilters({});
    setExpandedFilterGroups({});
    setDocumentStep("idle");
    setDocumentMessage("");
    setDocumentMessageMode(null);
    setPendingAction(null);
    setAttemptedFileName("");
    setQueueItems([]);
    setActiveQueueItemId(null);
    setIsQueueRunning(false);
  }, [refreshRevision]);

  const currentFileLabel = useMemo(() => {
    if (
      (documentStep === "uploading" || documentStep === "processing" || documentStep === "indexing") &&
      attemptedFileName
    ) {
      return String(attemptedFileName);
    }
    const candidate =
      documentState.uploadedDocument?.file_name ||
      documentState.uploadedDocument?.filename ||
      documentState.uploadedDocument?.original_filename ||
      attemptedFileName ||
      currentFilePath ||
      "No file selected";
    return String(candidate);
  }, [attemptedFileName, currentFilePath, documentState.uploadedDocument]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = draft.trim();
    if (!content || isSending) return;

    setError("");
    setDraft("");
    setIsSending(true);

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };
    onMessagesChange([...messages, userMessage]);

    try {
      const requestFilters = expandFiltersForRequest(selectedFilters, filterGroups);
      const response = await sendChatMessage(
        token,
        sessionId,
        content,
        Object.keys(requestFilters).length > 0 ? requestFilters : undefined,
      );
      onSessionChange(response.session_id);
      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: response.answer,
        createdAt: new Date().toISOString(),
      };
      onMessagesChange([...messages, userMessage, assistantMessage]);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Could not send message.");
      onMessagesChange([...messages, userMessage]);
    } finally {
      setIsSending(false);
      inputRef.current?.focus();
    }
  }

  function toggleFilterValue(key: string, value: string) {
    setSelectedFilters((previous) => {
      const currentValues = previous[key] || [];
      const nextValues = currentValues.includes(value)
        ? currentValues.filter((entry) => entry !== value)
        : [...currentValues, value];
      if (nextValues.length === 0) {
        const { [key]: _removed, ...rest } = previous;
        return rest;
      }
      return { ...previous, [key]: nextValues };
    });
  }

  function toggleFilterGroup(groupId: string) {
    setExpandedFilterGroups((previous) => ({
      ...previous,
      [groupId]: !previous[groupId],
    }));
  }

  function handleDocumentUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length === 0 || !canUploadNewDocument || isQueueRunning) {
      return;
    }

    const newItems: QueueItem[] = files.map((file) => ({
      id: crypto.randomUUID(),
      file,
      fileName: file.name,
      storageProvider,
      metadataPairs: [{ id: crypto.randomUUID(), key: "", value: "" }],
      state: "waiting",
      action: "new",
      label: "New",
      message: "Waiting to start.",
    }));

    setQueueItems((previous) => [...previous, ...newItems]);
  }

  function updateQueueItem(itemId: string, updater: (item: QueueItem) => QueueItem) {
    setQueueItems((previous) => previous.map((item) => (item.id === itemId ? updater(item) : item)));
  }

  async function runQueueItem(itemId: string) {
    const item = queueItems.find((entry) => entry.id === itemId);
    if (!item) {
      return;
    }

    setIsQueueRunning(true);
    setActiveQueueItemId(itemId);
    setAttemptedFileName(item.fileName);
    setDocumentMessageMode("fresh");
    setError("");

    updateQueueItem(itemId, (current) => ({
      ...current,
      state: "checking",
      message: "Checking current document state...",
    }));

    try {
      await executeQueueItem(item);
    } finally {
      setActiveQueueItemId(null);
      setIsQueueRunning(false);
    }
  }

  async function handleStartQueue() {
    if (isQueueRunning) {
      return;
    }

    while (true) {
      const nextItem = queueItemsRef.current.find((item) => item.state === "waiting");
      if (!nextItem) {
        break;
      }
      await runQueueItem(nextItem.id);
    }
  }

  function handleRemoveQueueItem(itemId: string) {
    if (isQueueRunning && itemId === activeQueueItemId) {
      return;
    }
    setQueueItems((previous) => previous.filter((item) => item.id !== itemId));
  }

  function updateQueueItemMetadataPair(
    itemId: string,
    pairId: string,
    field: "key" | "value",
    value: string,
  ) {
    updateQueueItem(itemId, (current) => ({
      ...current,
      metadataPairs: current.metadataPairs.map((pair) =>
        pair.id === pairId ? { ...pair, [field]: value } : pair,
      ),
    }));
  }

  function addQueueItemMetadataPair(itemId: string) {
    updateQueueItem(itemId, (current) => ({
      ...current,
      metadataPairs: [...current.metadataPairs, { id: crypto.randomUUID(), key: "", value: "" }],
    }));
  }

  function removeQueueItemMetadataPair(itemId: string, pairId: string) {
    updateQueueItem(itemId, (current) => {
      const nextPairs = current.metadataPairs.filter((pair) => pair.id !== pairId);
      return {
        ...current,
        metadataPairs: nextPairs,
      };
    });
  }

  async function executeQueueItem(item: QueueItem) {
    let uploadedDocument: UploadedDocument | null = null;
    let filePath = item.filePath || "";
    let action: QueueAction = item.action;
    let actionLabel = item.label;
    let message = item.message;
    let successMessageMode: DocumentMessageMode = "fresh";
    let uploadedInCurrentRun = false;
    let processedInCurrentRun = false;
    let failedStage: StepAction = action === "index" || action === "retry-index" ? "index" : action === "process" || action === "retry-process" ? "process" : "upload";

    try {
      if (action === "new" || action === "retry-upload") {
        failedStage = "upload";
        setDocumentStep("uploading");
        setPendingAction("upload");
        setDocumentMessage("Uploading document...");
        updateQueueItem(item.id, (current) => ({
          ...current,
          state: "running",
          action,
          label: action === "retry-upload" ? "Retry upload" : "New",
          message: "Uploading document...",
        }));

        try {
          const metadata = buildMetadataFromPairs(item.metadataPairs);
          uploadedDocument = await uploadDocument(
            item.file,
            item.storageProvider,
            Object.keys(metadata).length > 0 ? metadata : undefined,
          );
          filePath = String(uploadedDocument.file_path || "").trim();
          if (!filePath) {
            throw new Error("Upload completed but no file path was returned.");
          }
          uploadedInCurrentRun = true;
          onUploadedDocument(uploadedDocument);
          void reloadMetadataOptions();
          action = "process";
          actionLabel = "Continue processing";
          message = "Document uploaded. Continue with processing.";
          updateQueueItem(item.id, (current) => ({
            ...current,
            documentId: String(uploadedDocument?.document_id || ""),
            filePath,
            action,
            label: actionLabel,
            message,
          }));
        } catch (uploadError) {
          const detail = uploadError instanceof Error ? uploadError.message : "Upload failed.";
          const existingDocumentId = extractDocumentIdFromMessage(detail);

          if (existingDocumentId) {
            const restoredState = await refreshDocumentStateByDocumentId(existingDocumentId);
            const decision = deriveQueueActionFromState(restoredState);
            filePath = String(restoredState.uploaded_document?.file_path || "").trim();
            uploadedDocument = restoredState.uploaded_document ?? null;
            if (uploadedDocument) {
              onUploadedDocument(uploadedDocument);
            }
            action = decision.action;
            actionLabel = decision.label;
            message = decision.message;
            successMessageMode =
              decision.action === "done"
                ? "existing-indexed"
                : decision.action === "index"
                  ? "resume-from-processed"
                  : decision.action === "process"
                    ? "resume-from-uploaded"
                    : "fresh";
            setDocumentMessageMode(successMessageMode);
            updateQueueItem(item.id, (current) => ({
              ...current,
              state: decision.action === "done" ? "done" : "running",
              documentId: existingDocumentId,
              filePath,
              action: decision.action,
              label: decision.label,
              message: decision.message,
            }));

            if (decision.action === "done") {
              setDocumentStep("done");
              setPendingAction(null);
              setDocumentMessage(decision.message);
              return;
            }
          } else {
            throw uploadError;
          }
        }
      }

      if (!filePath && item.documentId) {
        const restoredState = await refreshDocumentStateByDocumentId(item.documentId);
        filePath = String(restoredState.uploaded_document?.file_path || "").trim();
        const decision = deriveQueueActionFromState(restoredState);
        action = decision.action;
        actionLabel = decision.label;
        message = decision.message;
        updateQueueItem(item.id, (current) => ({
          ...current,
          filePath,
          action,
          label: actionLabel,
          message,
        }));
      }

      if ((action === "process" || action === "retry-process") && filePath) {
        if (!uploadedInCurrentRun && successMessageMode === "fresh") {
          successMessageMode = "resume-from-uploaded";
          setDocumentMessageMode(successMessageMode);
        }
        failedStage = "process";
        setDocumentStep("processing");
        setPendingAction("process");
        setDocumentMessage("Extracting document content...");
        updateQueueItem(item.id, (current) => ({
          ...current,
          state: "running",
          filePath,
          action,
          label: action === "retry-process" ? "Retry processing" : "Continue processing",
          message: "Extracting document content...",
        }));
        const processed = await runProcessWithFallback(filePath);
        processedInCurrentRun = true;
        onPipelineResult(processed);
        action = "index";
        actionLabel = "Continue indexing";
        message = "Document already uploaded and parsed. Continue with indexing.";
        updateQueueItem(item.id, (current) => ({
          ...current,
          filePath,
          action,
          label: actionLabel,
          message,
        }));
      }

      if ((action === "index" || action === "retry-index") && filePath) {
        if (!uploadedInCurrentRun && !processedInCurrentRun && successMessageMode === "fresh") {
          successMessageMode = "resume-from-processed";
          setDocumentMessageMode(successMessageMode);
        }
        failedStage = "index";
        setDocumentStep("indexing");
        setPendingAction("index");
        setDocumentMessage("Indexing document in LightRAG...");
        updateQueueItem(item.id, (current) => ({
          ...current,
          state: "running",
          filePath,
          action,
          label: action === "retry-index" ? "Retry indexing" : "Continue indexing",
          message: "Indexing document in LightRAG...",
        }));
        const indexed = await runIndexingWithFallback(filePath);
        onIndexingResult(indexed);
      }

      setDocumentStep("done");
      setPendingAction(null);
      setDocumentMessage(getSuccessMessage(successMessageMode));
      updateQueueItem(item.id, (current) => ({
        ...current,
        state: "done",
        action: "done",
        label: current.label === "Already indexed" ? "Already indexed" : "Done",
        message: current.label === "Already indexed" ? getSuccessMessage("existing-indexed") : getSuccessMessage(successMessageMode),
      }));
    } catch (itemError) {
      const detail = itemError instanceof Error ? itemError.message : "Step failed.";
      setDocumentStep("error");
      setPendingAction(null);
      setDocumentMessage(detail);

      const nextAction: QueueAction =
        failedStage === "upload"
          ? "retry-upload"
          : failedStage === "process"
            ? "retry-process"
            : "retry-index";
      const nextLabel =
        nextAction === "retry-upload"
          ? "Retry upload"
          : nextAction === "retry-process"
            ? "Retry processing"
            : "Retry indexing";

      updateQueueItem(item.id, (current) => ({
        ...current,
        state: "error",
        documentId: current.documentId || uploadedDocument?.document_id?.toString(),
        filePath: filePath || current.filePath,
        action: nextAction,
        label: nextLabel,
        message: detail,
      }));
    }
  }

  async function refreshCurrentDocumentState(filePath: string) {
    const state = await getDocumentState(filePath);
    if (state.uploaded_document) {
      onUploadedDocument(state.uploaded_document);
    }
    if (state.latest_processing) {
      onPipelineResult({
        uploaded_document: state.uploaded_document ?? documentState.uploadedDocument ?? null,
        docling_result: documentState.pipelineResult?.docling_result ?? null,
        latest_processing: state.latest_processing,
        confidence_source: documentState.pipelineResult?.confidence_source ?? null,
        confidence_value: documentState.pipelineResult?.confidence_value ?? null,
        vlm_triggered: Boolean(state.latest_processing.used_vlm),
        vlm_result: documentState.pipelineResult?.vlm_result ?? null,
        final_markdown:
          typeof state.latest_processing.markdown_text === "string"
            ? state.latest_processing.markdown_text
            : documentState.pipelineResult?.final_markdown ?? null,
        final_message: `Document ${String(state.latest_processing.processing_status || "updated")}.`,
      });
    }
    if (state.indexing_result) {
      onIndexingResult({
        file_path: filePath,
        document_id: state.indexing_result.document_id ?? state.uploaded_document?.document_id,
        indexing_result: state.indexing_result,
      });
    } else {
      onIndexingResult(null);
    }
    return state;
  }

  async function refreshDocumentStateByDocumentId(documentId: string) {
    const state = await getDocumentStateByDocumentId(documentId);
    if (state.uploaded_document) {
      onUploadedDocument(state.uploaded_document);
    }
    if (state.latest_processing) {
      onPipelineResult({
        uploaded_document: state.uploaded_document ?? documentState.uploadedDocument ?? null,
        docling_result: documentState.pipelineResult?.docling_result ?? null,
        latest_processing: state.latest_processing,
        confidence_source: documentState.pipelineResult?.confidence_source ?? null,
        confidence_value: documentState.pipelineResult?.confidence_value ?? null,
        vlm_triggered: Boolean(state.latest_processing.used_vlm),
        vlm_result: documentState.pipelineResult?.vlm_result ?? null,
        final_markdown:
          typeof state.latest_processing.markdown_text === "string"
            ? state.latest_processing.markdown_text
            : documentState.pipelineResult?.final_markdown ?? null,
        final_message: `Document ${String(state.latest_processing.processing_status || "updated")}.`,
      });
    }
    if (state.indexing_result) {
      onIndexingResult({
        file_path: state.uploaded_document?.file_path,
        document_id: state.indexing_result.document_id ?? state.uploaded_document?.document_id,
        indexing_result: state.indexing_result,
      });
    } else {
      onIndexingResult(null);
    }
    return state;
  }

  async function handleContinueStep(action: Exclude<StepAction, null>) {
    if (!currentFilePath) return;

    setError("");
    setPendingAction(action);

    try {
      if (action === "process") {
        setDocumentMessageMode("fresh");
        setDocumentStep("processing");
        setDocumentMessage("Extracting document content...");
        const processed = await runProcessWithFallback(currentFilePath);
        onPipelineResult(processed);

        setDocumentStep("indexing");
        setPendingAction("index");
        setDocumentMessage("Indexing document in LightRAG...");
        const indexed = await runIndexingWithFallback(currentFilePath);
        onIndexingResult(indexed);

        setDocumentStep("done");
        setPendingAction(null);
        setDocumentMessage(getSuccessMessage("resume-from-uploaded"));
        return;
      }

      if (action === "index") {
        setDocumentMessageMode("fresh");
        setDocumentStep("indexing");
        setDocumentMessage("Indexing document in LightRAG...");
        const indexed = await runIndexingWithFallback(currentFilePath);
        onIndexingResult(indexed);

        setDocumentStep("done");
        setPendingAction(null);
        setDocumentMessage(getSuccessMessage("resume-from-processed"));
        return;
      }

      fileInputRef.current?.click();
    } catch (actionError) {
      setDocumentStep("error");
      setDocumentMessage(actionError instanceof Error ? actionError.message : "Step failed.");
      setPendingAction(null);
    }
  }

  async function runProcessWithFallback(filePath: string): Promise<PipelineResponse> {
    try {
      return await processDocument(filePath, "auto");
    } catch (error) {
      const state = await pollDocumentState(
        filePath,
        (candidate) =>
          candidate.uploaded_document?.status === "parsed" ||
          candidate.uploaded_document?.status === "indexed" ||
          Boolean(candidate.latest_processing?.markdown_text),
      );
      if (!state) {
        throw error;
      }
      if (state.uploaded_document) {
        onUploadedDocument(state.uploaded_document);
      }
      const pipelineState: PipelineResponse = {
        uploaded_document: state.uploaded_document ?? null,
        docling_result: null,
        latest_processing: state.latest_processing ?? null,
        confidence_source: null,
        confidence_value: null,
        vlm_triggered: Boolean(state.latest_processing?.used_vlm),
        vlm_result: null,
        final_markdown:
          typeof state.latest_processing?.markdown_text === "string"
            ? state.latest_processing.markdown_text
            : null,
        final_message: "Document parsed.",
      };
      onPipelineResult(pipelineState);
      if (isErrorStatus(state.latest_processing?.processing_status)) {
        throw new Error(String(state.latest_processing?.error_message || "Processing failed."));
      }
      return pipelineState;
    }
  }

  async function runIndexingWithFallback(filePath: string): Promise<IndexingResponse> {
    try {
      return await indexDocument(filePath);
    } catch (error) {
      const state = await pollDocumentState(
        filePath,
        (candidate) => candidate.uploaded_document?.status === "indexed" || candidate.indexing_result?.status === "indexed",
      );
      if (!state) {
        throw error;
      }
      if (state.uploaded_document) {
        onUploadedDocument(state.uploaded_document);
      }
      const indexingState: IndexingResponse = {
        file_path: filePath,
        document_id: state.indexing_result?.document_id ?? state.uploaded_document?.document_id,
        indexing_result: state.indexing_result ?? { status: "indexed" },
      };
      onIndexingResult(indexingState);
      if (isErrorStatus(state.indexing_result?.status)) {
        throw new Error(
          String(state.indexing_result?.error || state.indexing_result?.error_message || "Indexing failed."),
        );
      }
      return indexingState;
    }
  }

  async function pollDocumentState(
    filePath: string,
    predicate: (state: DocumentStateResponse) => boolean,
  ): Promise<DocumentStateResponse | null> {
    const deadline = Date.now() + DOCUMENT_POLL_TIMEOUT_MS;
    while (Date.now() < deadline) {
      const state = await getDocumentState(filePath);
      if (isErrorStatus(state.latest_processing?.processing_status) || isErrorStatus(state.indexing_result?.status)) {
        return state;
      }
      if (predicate(state)) {
        if (state.uploaded_document) {
          onUploadedDocument(state.uploaded_document);
        }
        return state;
      }
      await new Promise((resolve) => window.setTimeout(resolve, DOCUMENT_POLL_INTERVAL_MS));
    }
    return null;
  }

  return (
    <section className="chat-layout">
      <div className="chat-main">
        <div className="surface-header">
          <div>
            <p className="eyebrow">Conversation</p>
            <h2>Ask the assistant</h2>
          </div>
          <button className="secondary-button" type="button" onClick={onNewChat}>
            <Plus size={16} aria-hidden="true" />
            New chat
          </button>
        </div>

        <div className="message-list" aria-live="polite">
          {messages.map((message) => (
            <article key={message.id} className={`message ${message.role}`}>
              <div className="message-body">
                <div className="message-meta">
                  <strong>{message.role === "assistant" ? "Assistant" : "You"}</strong>
                  <span>{new Date(message.createdAt).toLocaleTimeString()}</span>
                </div>
                {renderMessageContent(message.content)}
              </div>
            </article>
          ))}
          {isSending && (
            <article className="message assistant">
              <div className="message-avatar">
                <Sparkles size={18} aria-hidden="true" />
              </div>
              <div className="message-body muted-text">Thinking with the current knowledge base...</div>
            </article>
          )}
        </div>

        {error && <div className="error-banner">{error}</div>}

        <form className="chat-input" onSubmit={handleSubmit}>
          <div className="chat-compose">
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ask about uploaded and indexed documents..."
              rows={3}
            />
            <div className="chat-toolbar">
              <button
                type="button"
                className={`secondary-button filter-toggle-button${hasActiveFilters ? " active" : ""}`}
                onClick={() => setShowFilters((previous) => !previous)}
              >
                <Filter size={16} aria-hidden="true" />
                Filter
                <ChevronDown size={16} aria-hidden="true" className={showFilters ? "rotate-icon" : ""} />
              </button>
              {showFilters && (
                <div className="metadata-filter-panel">
                  {filterGroups.length === 0 ? (
                    <p className="muted-text">No metadata filters available yet.</p>
                  ) : (
                    filterGroups.map((group) => {
                      const expanded = expandedFilterGroups[group.id] ?? false;
                      return (
                        <div key={group.id} className="metadata-filter-group">
                          <button
                            type="button"
                            className="metadata-filter-group-toggle"
                            onClick={() => toggleFilterGroup(group.id)}
                          >
                            <strong>{group.label}</strong>
                            <ChevronDown
                              size={16}
                              aria-hidden="true"
                              className={expanded ? "rotate-icon" : ""}
                            />
                          </button>
                          {expanded && (
                            <div className="metadata-filter-group-values">
                              {group.values.map((value) => {
                                const checked = (selectedFilters[group.id] || []).includes(value);
                                return (
                                  <label key={`${group.id}:${value}`} className="metadata-filter-option">
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={() => toggleFilterValue(group.id, value)}
                                    />
                                    <span>{value}</span>
                                  </label>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}
              <button className="primary-button send-button" type="submit" disabled={isSending || !draft.trim()}>
                <Send size={18} aria-hidden="true" />
                Send
              </button>
            </div>
          </div>
        </form>
      </div>

      <aside className="side-panel">
        <div className="surface-header compact">
          <div>
            <p className="eyebrow">Document</p>
            <h2>Uploaded document</h2>
          </div>
          <StatusBadge
            label={documentStep === "done" ? "Ready" : documentStep === "error" ? "Error" : knowledgeState}
            tone={knowledgeState === "Indexed" ? "ok" : knowledgeState === "No document" ? "warning" : "neutral"}
          />
        </div>

        <div className="document-upload-panel">
          <label className="field-label" htmlFor="storage-provider">
            Storage provider
          </label>
          <select
            id="storage-provider"
            className="provider-select"
            value={storageProvider}
            onChange={(event) => setStorageProvider(event.target.value as StorageProvider)}
            disabled={!canUploadNewDocument || isQueueRunning}
          >
            <option value="nextcloud">Nextcloud</option>
            <option value="onedrive">OneDrive</option>
            <option value="sharepoint">SharePoint</option>
          </select>

          <label className="file-picker compact-picker">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleDocumentUpload}
              disabled={!canUploadNewDocument}
            />
            <FileUp size={22} aria-hidden="true" />
            <span>{isQueueRunning ? "Queue running..." : "Choose documents to add to queue · try PDF, Word, CSV, or TXT"}</span>
          </label>

          {queueItems.length > 0 && (
            <div className="queue-summary">
              <div className="queue-summary-main">
                <strong>
                  {queueCompletedCount}/{queueItems.length}
                </strong>
                <span>documents completed</span>
              </div>
              <div className="queue-summary-meta">
                <span>{queueItems.filter((item) => item.state === "waiting").length} waiting</span>
                <span>{queueRunningCount} running</span>
                <span>{queueErrorCount} error</span>
              </div>
            </div>
          )}

          <div className="document-progress">
            <ProgressRow
              label="Upload"
              status={uploadRowStatus}
              action={!isQueueRunning && documentStep === "error" && !uploadDone && canUploadNewDocument ? "upload" : null}
              busy={pendingAction === "upload"}
              onAction={() => void handleContinueStep("upload")}
            />
            <ProgressRow
              label="Processing"
              status={processRowStatus}
              action={!isQueueRunning && uploadDone && (!processDone || processFailed) ? "process" : null}
              busy={pendingAction === "process"}
              onAction={() => void handleContinueStep("process")}
            />
            <ProgressRow
              label="Indexing"
              status={indexRowStatus}
              action={!isQueueRunning && uploadDone && processDone && !processFailed && !indexingDone ? "index" : null}
              busy={pendingAction === "index"}
              onAction={() => void handleContinueStep("index")}
            />
          </div>

          {documentMessage && (
            <div className={documentStep === "error" ? "error-banner" : "notice-banner"}>{documentMessage}</div>
          )}

          {queueItems.length > 0 && (
            <div className="queue-list">
              {queueItems.map((item, index) => (
                <QueueRow
                  key={item.id}
                  index={index + 1}
                  item={item}
                  active={item.id === activeQueueItemId}
                  disabled={isQueueRunning && item.id !== activeQueueItemId}
                  onMetadataPairChange={updateQueueItemMetadataPair}
                  onAddMetadataPair={addQueueItemMetadataPair}
                  onRemoveMetadataPair={removeQueueItemMetadataPair}
                  onRetry={() => void runQueueItem(item.id)}
                  onRemove={() => handleRemoveQueueItem(item.id)}
                />
              ))}
            </div>
          )}

          {queueItems.length > 0 && (
            <div className="queue-actions">
              <button
                type="button"
                className="primary-button full-width"
                onClick={() => void handleStartQueue()}
                disabled={isQueueRunning || !queueItems.some((item) => item.state === "waiting")}
              >
                {isQueueRunning ? <Loader2 size={16} aria-hidden="true" className="spin-icon" /> : <Play size={16} aria-hidden="true" />}
                Start
              </button>
            </div>
          )}
        </div>

        <div className="info-list">
          <div>
            <span>Current file</span>
            <strong>{currentFileLabel}</strong>
          </div>
          <div>
            <span>Status</span>
            <strong>{knowledgeState}</strong>
          </div>
        </div>
      </aside>
    </section>
  );
}

function ProgressRow({
  label,
  status,
  action,
  busy,
  onAction,
}: {
  label: string;
  status: StepVisualStatus;
  action: StepAction;
  busy: boolean;
  onAction: () => void;
}) {
  const Icon = status === "error" ? AlertCircle : status === "active" ? Loader2 : status === "done" ? CheckCircle2 : null;
  const ActionIcon = status === "error" ? RefreshCw : Play;
  const actionLabel =
    action === "upload"
      ? status === "error"
        ? "Retry upload"
        : "Upload document"
      : action === "process"
        ? status === "error"
          ? "Retry processing"
          : "Run processing"
        : status === "error"
          ? "Retry indexing"
          : "Run indexing";
  return (
    <div
      className={
        status === "active"
          ? "progress-row active"
          : status === "error"
            ? "progress-row error"
            : status === "done"
              ? "progress-row done"
              : "progress-row"
      }
    >
      <span>{Icon ? <Icon size={16} aria-hidden="true" /> : <span className="progress-dot" />}</span>
      <strong>{label}</strong>
      {action && (
        <button
          type="button"
          className="progress-row-action"
          onClick={onAction}
          disabled={busy}
          aria-label={actionLabel}
          title={status === "error" ? "Retry" : "Continue"}
        >
          {busy ? <Loader2 size={15} aria-hidden="true" /> : <ActionIcon size={15} aria-hidden="true" />}
        </button>
      )}
    </div>
  );
}

function QueueRow({
  index,
  item,
  active,
  disabled,
  onMetadataPairChange,
  onAddMetadataPair,
  onRemoveMetadataPair,
  onRetry,
  onRemove,
}: {
  index: number;
  item: QueueItem;
  active: boolean;
  disabled: boolean;
  onMetadataPairChange: (itemId: string, pairId: string, field: "key" | "value", value: string) => void;
  onAddMetadataPair: (itemId: string) => void;
  onRemoveMetadataPair: (itemId: string, pairId: string) => void;
  onRetry: () => void;
  onRemove: () => void;
}) {
  const metadata = buildMetadataFromPairs(item.metadataPairs);

  const icon =
    item.state === "done" ? (
      <CheckCircle2 size={15} aria-hidden="true" />
    ) : item.state === "error" ? (
      <AlertCircle size={15} aria-hidden="true" />
    ) : item.state === "running" || item.state === "checking" ? (
      <Loader2 size={15} aria-hidden="true" className="spin-icon" />
    ) : (
      <Clock3 size={15} aria-hidden="true" />
    );

  const canRetry = item.state === "error";
  const canRemove = item.state !== "running" && item.state !== "checking";
  const canEditMetadata = item.state === "waiting" || item.state === "error";

  const rowClass =
    item.state === "done"
      ? "queue-row done"
      : item.state === "error"
        ? "queue-row error"
        : item.state === "running" || item.state === "checking"
          ? "queue-row active"
          : "queue-row";

  return (
    <div className={rowClass}>
      <div className="queue-row-main">
        <div className="queue-row-top">
          <div className="queue-row-title">
            <span className="queue-row-index">{index}</span>
            <strong>{item.fileName}</strong>
          </div>

          <div className="queue-row-side">
            <span className="queue-row-icon">{icon}</span>

            {canRetry && (
              <button
                type="button"
                className="progress-row-action"
                onClick={onRetry}
                disabled={disabled}
                aria-label={`Retry ${item.fileName}`}
                title="Retry"
              >
                <RefreshCw size={15} aria-hidden="true" />
              </button>
            )}

            {canRemove && (
              <button
                type="button"
                className="progress-row-action queue-remove-action"
                onClick={onRemove}
                disabled={disabled}
                aria-label={`Remove ${item.fileName}`}
                title="Remove from queue"
              >
                <CircleX size={15} aria-hidden="true" />
              </button>
            )}
          </div>
        </div>

        <div className="queue-row-meta">
          <span>{item.label}</span>
          {active && <span>Current</span>}
        </div>

        <div className="queue-row-message">{item.message}</div>

        {canEditMetadata ? (
          <div className="queue-row-metadata-editor">
            <div className="queue-row-metadata-title">
              <span className="queue-row-metadata-label">Metadata</span>

              <button
                type="button"
                className="icon-text-button small-button metadata-add-button"
                onClick={() => onAddMetadataPair(item.id)}
                disabled={disabled}
                aria-label="Add metadata"
                title="Add metadata"
              >
                <Plus size={16} aria-hidden="true" />
              </button>
            </div>

            <p className="queue-row-metadata-help">
              Optionally add key-value pairs to help filter this file.
            </p>

            <div className="metadata-pairs">
              {item.metadataPairs.map((pair) => (
                <div key={pair.id} className="metadata-pair-row">
                  <input
                    type="text"
                    value={pair.key}
                    onChange={(event) => onMetadataPairChange(item.id, pair.id, "key", event.target.value)}
                    placeholder="Field name"
                    disabled={disabled}
                  />

                  <input
                    type="text"
                    value={pair.value}
                    onChange={(event) => onMetadataPairChange(item.id, pair.id, "value", event.target.value)}
                    placeholder="Field value"
                    disabled={disabled}
                  />

                  <button
                    type="button"
                    className="progress-row-action queue-remove-action metadata-remove-button"
                    onClick={() => onRemoveMetadataPair(item.id, pair.id)}
                    disabled={disabled}
                    aria-label="Remove metadata field"
                    title="Remove metadata field"
                  >
                    <CircleX size={15} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : Object.keys(metadata).length > 0 ? (
          <div className="queue-row-tags">
            {Object.entries(metadata).map(([key, value]) => (
              <span key={`${item.id}:${key}`} className="queue-row-tag">
                {key}: {value}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function extractDocumentIdFromMessage(message: string): string | null {
  const match = message.match(/document_id=([0-9a-fA-F-]+)/);
  return match?.[1] || null;
}
