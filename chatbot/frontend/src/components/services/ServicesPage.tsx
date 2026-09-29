import { ChangeEvent, FormEvent, ReactNode, useState } from "react";
import {
  ChevronDown,
  Database,
  FileSearch,
  Layers,
  RefreshCw,
  UploadCloud,
} from "lucide-react";
import {
  indexDocument,
  initializeDatabase,
  processDocument,
  uploadDocument,
} from "../../lib/api";
import type {
  IndexingResponse,
  PipelineResponse,
  ServiceCard as ServiceCardType,
  ServiceStatusResponse,
  UploadedDocument,
} from "../../types";
import { StatusBadge } from "../shared/StatusBadge";

type ServicesPageProps = {
  serviceStatus: ServiceStatusResponse | null;
  uploadedDocument: UploadedDocument | null;
  pipelineResult: PipelineResponse | null;
  indexingResult: IndexingResponse | null;
  onRefreshStatus: () => Promise<void>;
  onUploadedDocument: (document: UploadedDocument) => void;
  onPipelineResult: (result: PipelineResponse) => void;
  onIndexingResult: (result: IndexingResponse) => void;
};

export function ServicesPage({
  serviceStatus,
  uploadedDocument,
  pipelineResult,
  indexingResult,
  onRefreshStatus,
  onUploadedDocument,
  onPipelineResult,
  onIndexingResult,
}: ServicesPageProps) {
  const [openPanel, setOpenPanel] = useState("upload");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [filePath, setFilePath] = useState(uploadedDocument?.file_path || "");
  const [languageHint, setLanguageHint] = useState("auto");
  const [busyAction, setBusyAction] = useState("");
  const [message, setMessage] = useState("");
  const isProcessed =
    Boolean(pipelineResult?.final_markdown) ||
    uploadedDocument?.status === "parsed" ||
    uploadedDocument?.status === "indexed";
  const indexingStatus =
    indexingResult?.indexing_result?.status ||
    (uploadedDocument?.status === "indexed" ? "indexed" : "");

  function togglePanel(panel: string) {
    setOpenPanel(openPanel === panel ? "" : panel);
  }

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;
    setSelectedFile(file);
  }

  async function handleInitDatabase() {
    setBusyAction("database");
    setMessage("");
    try {
      await initializeDatabase();
      setMessage("Database tables initialized.");
      await onRefreshStatus();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Database initialization failed.");
    } finally {
      setBusyAction("");
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setMessage("Choose a file first.");
      return;
    }

    setBusyAction("upload");
    setMessage("");
    try {
      const document = await uploadDocument(selectedFile);
      onUploadedDocument(document);
      setFilePath(document.file_path || "");
      setMessage("Document uploaded.");
      await onRefreshStatus();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setBusyAction("");
    }
  }

  async function handleProcess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!filePath.trim()) {
      setMessage("A file path is required.");
      return;
    }

    setBusyAction("process");
    setMessage("");
    try {
      const result = await processDocument(filePath.trim(), languageHint);
      onPipelineResult(result);
      setMessage(result.final_message || "Document processed.");
      await onRefreshStatus();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Processing failed.");
    } finally {
      setBusyAction("");
    }
  }

  async function handleIndex(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!filePath.trim()) {
      setMessage("A file path is required.");
      return;
    }

    setBusyAction("index");
    setMessage("");
    try {
      const result = await indexDocument(filePath.trim());
      onIndexingResult(result);
      setMessage("Document indexed in LightRAG.");
      await onRefreshStatus();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Indexing failed.");
    } finally {
      setBusyAction("");
    }
  }

  return (
    <section className="services-layout">
      <article className="surface">
        <div className="surface-header">
          <div>
            <p className="eyebrow">Services</p>
            <h2>Operational overview</h2>
          </div>
          <button className="secondary-button" type="button" onClick={() => void onRefreshStatus()}>
            <RefreshCw size={16} aria-hidden="true" />
            Refresh
          </button>
        </div>

        <div className="service-status-grid">
          <ServiceHealth name="Orchestration" card={serviceStatus?.orchestration} />
          <ServiceHealth name="Storage" card={serviceStatus?.storage} />
          <ServiceHealth name="Postgres" card={serviceStatus?.postgres} />
          <ServiceHealth name="Upload" card={serviceStatus?.upload} />
          <ServiceHealth name="Docling" card={serviceStatus?.docling} />
          <ServiceHealth name="VLM" card={serviceStatus?.vlm} />
          <ServiceHealth name="LightRAG" card={serviceStatus?.lightrag} />
        </div>
      </article>

      {message && <div className="notice-banner">{message}</div>}

      <ServicePanel
        id="database"
        title="Database setup"
        description="Initialize or validate the tables used by the services."
        icon={Database}
        isOpen={openPanel === "database"}
        statusLabel={serviceStatus?.postgres?.reachable ? "Reachable" : "Check"}
        onToggle={() => togglePanel("database")}
      >
        <div className="panel-action-row">
          <p className="muted-text">Use this only when the environment needs table initialization.</p>
          <button
            className="primary-button"
            type="button"
            disabled={busyAction === "database"}
            onClick={() => void handleInitDatabase()}
          >
            {busyAction === "database" ? "Initializing..." : "Initialize tables"}
          </button>
        </div>
      </ServicePanel>

      <ServicePanel
        id="upload"
        title="Upload service"
        description="Send a document to the upload service and keep its path for processing."
        icon={UploadCloud}
        isOpen={openPanel === "upload"}
        statusLabel={uploadedDocument ? "Uploaded" : "Ready"}
        onToggle={() => togglePanel("upload")}
      >
        <form className="service-form" onSubmit={handleUpload}>
          <label className="file-picker">
            <input type="file" onChange={handleFileChange} />
            <UploadCloud size={22} aria-hidden="true" />
            <span>{selectedFile ? selectedFile.name : "Choose or drop a file"}</span>
          </label>
          <button className="primary-button" type="submit" disabled={busyAction === "upload"}>
            {busyAction === "upload" ? "Uploading..." : "Upload document"}
          </button>
        </form>

        <div className="info-list compact-list">
          <div>
            <span>Last file path</span>
            <strong>{uploadedDocument?.file_path || "No upload yet"}</strong>
          </div>
          <div>
            <span>Document ID</span>
            <strong>{uploadedDocument?.document_id || "-"}</strong>
          </div>
        </div>
      </ServicePanel>

      <ServicePanel
        id="process"
        title="Docling / VLM processing"
        description="Extract document content. VLM is used only when orchestration decides it is needed."
        icon={FileSearch}
        isOpen={openPanel === "process"}
        statusLabel={isProcessed ? "Processed" : "Waiting"}
        onToggle={() => togglePanel("process")}
      >
        <form className="service-form stacked" onSubmit={handleProcess}>
          <label className="field">
            <span>File path</span>
            <textarea
              rows={3}
              value={filePath}
              onChange={(event) => setFilePath(event.target.value)}
              placeholder="Use the uploaded file path or paste one."
              required
            />
          </label>
          <label className="field">
            <span>OCR language</span>
            <select value={languageHint} onChange={(event) => setLanguageHint(event.target.value)}>
              <option value="auto">Auto</option>
              <option value="french">French + English</option>
              <option value="arabic">Arabic + English</option>
            </select>
          </label>
          <button className="primary-button" type="submit" disabled={busyAction === "process"}>
            {busyAction === "process" ? "Processing..." : "Process document"}
          </button>
        </form>

        <div className="metric-row">
          <Metric label="Confidence" value={formatOptionalNumber(pipelineResult?.confidence_value)} />
          <Metric label="Source" value={pipelineResult?.confidence_source || "-"} />
          <Metric label="VLM" value={pipelineResult ? (pipelineResult.vlm_triggered ? "Triggered" : "Not needed") : "-"} />
        </div>
      </ServicePanel>

      <ServicePanel
        id="index"
        title="LightRAG indexing"
        description="Make the processed document available for chatbot retrieval."
        icon={Layers}
        isOpen={openPanel === "index"}
        statusLabel={indexingStatus || "Waiting"}
        onToggle={() => togglePanel("index")}
      >
        <form className="service-form stacked" onSubmit={handleIndex}>
          <label className="field">
            <span>File path</span>
            <textarea
              rows={3}
              value={filePath}
              onChange={(event) => setFilePath(event.target.value)}
              placeholder="Use the uploaded file path or paste one."
              required
            />
          </label>
          <button className="primary-button" type="submit" disabled={busyAction === "index"}>
            {busyAction === "index" ? "Indexing..." : "Run indexing"}
          </button>
        </form>

        <div className="info-list compact-list">
          <div>
            <span>Status</span>
            <strong>{indexingStatus || "Not indexed yet"}</strong>
          </div>
          <div>
            <span>Run ID</span>
            <strong>{indexingResult?.indexing_result?.run_id || "-"}</strong>
          </div>
        </div>
      </ServicePanel>
    </section>
  );
}

type ServiceHealthProps = {
  name: string;
  card?: ServiceCardType;
};

function ServiceHealth({ name, card }: ServiceHealthProps) {
  const tone = !card ? "neutral" : card.reachable ? "ok" : card.configured ? "danger" : "warning";
  const label = !card ? "Unknown" : card.reachable ? "Online" : card.configured ? "Down" : "Not configured";

  return (
    <div className="health-item">
      <div>
        <strong>{name}</strong>
        <span>{card?.url || "No URL"}</span>
      </div>
      <StatusBadge label={label} tone={tone} />
    </div>
  );
}

type ServicePanelProps = {
  id: string;
  title: string;
  description: string;
  statusLabel: string;
  isOpen: boolean;
  icon: typeof Database;
  children: ReactNode;
  onToggle: () => void;
};

function ServicePanel({
  title,
  description,
  statusLabel,
  isOpen,
  icon: Icon,
  children,
  onToggle,
}: ServicePanelProps) {
  return (
    <article className={isOpen ? "service-panel open" : "service-panel"}>
      <button className="service-panel-trigger" type="button" onClick={onToggle}>
        <div className="service-panel-title">
          <div className="panel-icon">
            <Icon size={20} aria-hidden="true" />
          </div>
          <div>
            <h3>{title}</h3>
            <p>{description}</p>
          </div>
        </div>
        <div className="service-panel-meta">
          <StatusBadge label={statusLabel} />
          <ChevronDown size={18} aria-hidden="true" />
        </div>
      </button>
      {isOpen && <div className="service-panel-body">{children}</div>}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatOptionalNumber(value?: number | null) {
  if (value === undefined || value === null) return "-";
  return String(value);
}
