import { FileText, Loader2, Trash2 } from "lucide-react";
import type { DocumentLibraryItem } from "../../types";
import { StatusBadge } from "../shared/StatusBadge";

type DocumentsPageProps = {
  documents: DocumentLibraryItem[];
  isLoading: boolean;
  deletingDocumentId: string | null;
  onRefresh: () => void;
  onDelete: (document: DocumentLibraryItem) => void;
};

export function DocumentsPage({
  documents,
  isLoading,
  deletingDocumentId,
  onRefresh,
  onDelete,
}: DocumentsPageProps) {
  return (
    <section className="content-grid documents-page">
      <article className="surface wide documents-surface">
        <div className="surface-header">
          <div>
            <p className="eyebrow">Documents</p>
            <h2>All uploaded documents</h2>
          </div>
          <button className="secondary-button" type="button" onClick={onRefresh} disabled={isLoading}>
            {isLoading ? <Loader2 size={16} aria-hidden="true" className="spin-icon" /> : <FileText size={16} aria-hidden="true" />}
            {isLoading ? "Loading" : "Reload list"}
          </button>
        </div>

        <div className="documents-page-list">
          {documents.length === 0 ? (
            <p className="muted-text">No documents found.</p>
          ) : (
            documents.map((document) => {
              const documentId = String(document.document_id || "");
              const isDeleting = deletingDocumentId === documentId;
              return (
                <div key={documentId || String(document.file_path || Math.random())} className="documents-page-item">
                  <div className="documents-page-item-main">
                    <div className="documents-page-title-row">
                      <strong>{document.file_name || "Unnamed document"}</strong>
                      <StatusBadge
                        label={String(document.status || "unknown")}
                        tone={
                          document.status === "indexed"
                            ? "ok"
                            : document.status === "error"
                              ? "danger"
                              : "warning"
                        }
                      />
                    </div>
                    <div className="documents-page-meta">
                      <span><strong>Storage:</strong> {document.storage_backend || "-"}</span>
                      <span><strong>Updated:</strong> {document.updated_at || document.created_at || "-"}</span>
                    </div>
                    {document.metadata_json && Object.keys(document.metadata_json).length > 0 && (
                      <div className="documents-page-tags">
                        {Object.entries(document.metadata_json).map(([key, value]) => (
                          <span key={`${documentId}:${key}`} className="queue-row-tag">
                            {key}: {value}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="documents-page-actions">
                    <button
                      type="button"
                      className="progress-row-action queue-remove-action"
                      onClick={() => onDelete(document)}
                      disabled={isDeleting}
                      aria-label={`Delete ${document.file_name || "document"}`}
                      title="Delete totally"
                    >
                      {isDeleting ? (
                        <Loader2 size={15} aria-hidden="true" className="spin-icon" />
                      ) : (
                        <Trash2 size={15} aria-hidden="true" />
                      )}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </article>
    </section>
  );
}
