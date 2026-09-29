import { useEffect, useMemo, useState } from "react";
import type {
  ChatMessage,
  ChatSession,
  DocumentLibraryItem,
  IndexingResponse,
  PipelineResponse,
  ServiceStatusResponse,
  UploadedDocument,
  User,
  ViewKey,
} from "./types";
import {
  deleteDocumentEverywhere,
  deleteChatSession,
  getDocuments,
  getChatSessionMessages,
  getChatSessions,
  getCurrentUser,
  getDocumentState,
  getServiceStatus,
} from "./lib/api";
import { AuthGate } from "./components/AuthGate";
import { ConfigurationGate } from "./components/ConfigurationGate";
import { AppShell } from "./components/layout/AppShell";
import { ChatPage } from "./components/chat/ChatPage";
import { DocumentsPage } from "./components/documents/DocumentsPage";
import { SettingsPage } from "./components/settings/SettingsPage";
import { hasRuntimeConfig } from "./lib/runtimeConfig";

const tokenStorageKey = "rag_chatbot_token";
const userStorageKey = "rag_chatbot_user";

function getDocumentStorageKey(userId: string) {
  return `rag_chatbot_document_state:${userId}`;
}

export function App() {
  const [isConfigured, setIsConfigured] = useState(() => hasRuntimeConfig());
  const [isEditingConfig, setIsEditingConfig] = useState(false);
  const [token, setToken] = useState(() => localStorage.getItem(tokenStorageKey) || "");
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem(userStorageKey);
    return raw ? (JSON.parse(raw) as User) : null;
  });
  const [activeView, setActiveView] = useState<ViewKey>("chat");
  const [serviceStatus, setServiceStatus] = useState<ServiceStatusResponse | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [uploadedDocument, setUploadedDocument] = useState<UploadedDocument | null>(null);
  const [pipelineResult, setPipelineResult] = useState<PipelineResponse | null>(null);
  const [indexingResult, setIndexingResult] = useState<IndexingResponse | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Ask a question about your indexed documents when you are ready.",
      createdAt: new Date().toISOString(),
    },
  ]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [documents, setDocuments] = useState<DocumentLibraryItem[]>([]);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    getCurrentUser(token)
      .then((currentUser) => {
        setUser(currentUser);
        localStorage.setItem(userStorageKey, JSON.stringify(currentUser));
      })
      .catch(() => {
        setToken("");
        setUser(null);
        localStorage.removeItem(tokenStorageKey);
        localStorage.removeItem(userStorageKey);
      });
  }, [token]);

  useEffect(() => {
    if (!user?.user_id) return;
    const raw = localStorage.getItem(getDocumentStorageKey(user.user_id));
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as {
        uploadedDocument?: UploadedDocument | null;
        pipelineResult?: PipelineResponse | null;
        indexingResult?: IndexingResponse | null;
      };
      setUploadedDocument(parsed.uploadedDocument || null);
      setPipelineResult(parsed.pipelineResult || null);
      setIndexingResult(parsed.indexingResult || null);
    } catch {
      localStorage.removeItem(getDocumentStorageKey(user.user_id));
    }
  }, [user?.user_id]);

  useEffect(() => {
    if (!user?.user_id) return;
    localStorage.setItem(
      getDocumentStorageKey(user.user_id),
      JSON.stringify({
        uploadedDocument,
        pipelineResult,
        indexingResult,
      }),
    );
  }, [indexingResult, pipelineResult, uploadedDocument, user?.user_id]);

  async function loadDocumentStateByFilePath(filePath: string) {
    const documentState = await getDocumentState(filePath);
    if (!documentState.uploaded_document) {
      setUploadedDocument(null);
      setPipelineResult(null);
      setIndexingResult(null);
      return;
    }

    setUploadedDocument(documentState.uploaded_document);
    const latestProcessing = documentState.latest_processing;
    if (latestProcessing) {
      setPipelineResult({
        uploaded_document: documentState.uploaded_document || null,
        docling_result: null,
        latest_processing: latestProcessing,
        confidence_source: null,
        confidence_value: null,
        vlm_triggered: Boolean(latestProcessing.used_vlm),
        vlm_result: null,
        final_markdown:
          typeof latestProcessing.markdown_text === "string" ? latestProcessing.markdown_text : null,
        final_message:
          typeof latestProcessing.processing_status === "string"
            ? `Document ${latestProcessing.processing_status}.`
            : "Document state loaded.",
      });
    } else {
      setPipelineResult(null);
    }
    if (documentState.indexing_result) {
      setIndexingResult({
        file_path: filePath,
        document_id: documentState.indexing_result.document_id,
        indexing_result: documentState.indexing_result,
      });
    } else {
      setIndexingResult(null);
    }
  }

  async function refreshStatus() {
    setIsRefreshing(true);
    try {
      const status = await getServiceStatus();
      setServiceStatus(status);
      const currentFilePath =
        uploadedDocument?.file_path ||
        pipelineResult?.uploaded_document?.file_path ||
        indexingResult?.file_path;
      if (currentFilePath) {
        await loadDocumentStateByFilePath(currentFilePath);
      }
      await refreshDocuments();
      await refreshSessions();
      await refreshActiveSessionMessages(sessionId);
    } finally {
      setRefreshRevision((current) => current + 1);
      setIsRefreshing(false);
    }
  }

  async function refreshSessions() {
    if (!token) return;
    const nextSessions = await getChatSessions(token);
    setSessions(nextSessions);
  }

  async function refreshDocuments() {
    setIsLoadingDocuments(true);
    try {
      const nextDocuments = await getDocuments(200);
      setDocuments(nextDocuments);
    } finally {
      setIsLoadingDocuments(false);
    }
  }

  async function refreshActiveSessionMessages(targetSessionId: string | null) {
    if (!token || !targetSessionId) return;
    const history = await getChatSessionMessages(token, targetSessionId);
    if (history.length === 0) {
      setMessages([
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Ask a question about your indexed documents when you are ready.",
          createdAt: new Date().toISOString(),
        },
      ]);
      return;
    }
    setMessages(
      history.map((message) => ({
        id: message.message_id,
        role: message.role,
        content: message.content,
        createdAt: message.created_at || new Date().toISOString(),
      })),
    );
  }

  async function handleSelectSession(nextSessionId: string) {
    if (!token) return;
    setSessionId(nextSessionId);
    await refreshActiveSessionMessages(nextSessionId);
    setActiveView("chat");
  }

  async function handleDeleteSession(targetSessionId: string) {
    if (!token) return;
    const targetSession = sessions.find((session) => session.session_id === targetSessionId);
    const targetLabel = String(targetSession?.title || "this chat").trim();
    const confirmed = window.confirm(`Delete "${targetLabel}"?`);
    if (!confirmed) return;

    await deleteChatSession(token, targetSessionId);
    setSessions((previous) => previous.filter((session) => session.session_id !== targetSessionId));
    if (sessionId === targetSessionId) {
      handleNewChat();
    }
  }

  async function handleDeleteDocument(document: DocumentLibraryItem) {
    const label = String(document.file_name || document.file_path || "this document").trim();
    const confirmed = window.confirm(`Delete "${label}" from all services?`);
    if (!confirmed) return;

    const documentId = String(document.document_id || "").trim() || undefined;
    const filePath = String(document.file_path || "").trim() || undefined;
    setDeletingDocumentId(documentId || filePath || null);
    try {
      await deleteDocumentEverywhere(documentId, filePath);
      setDocuments((previous) =>
        previous.filter((item) => String(item.document_id || "") !== String(document.document_id || "")),
      );
      if (uploadedDocument?.document_id && uploadedDocument.document_id === document.document_id) {
        setUploadedDocument(null);
        setPipelineResult(null);
        setIndexingResult(null);
      }
    } finally {
      setDeletingDocumentId(null);
    }
  }

  function handleNewChat() {
    setSessionId(null);
    setMessages([
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Ask a question about your indexed documents when you are ready.",
        createdAt: new Date().toISOString(),
      },
    ]);
    setActiveView("chat");
  }

  useEffect(() => {
    if (token) {
      refreshStatus().catch(() => undefined);
      refreshSessions().catch(() => undefined);
      refreshDocuments().catch(() => undefined);
    }
  }, [token]);

  const documentState = useMemo(
    () => ({
      uploadedDocument,
      pipelineResult,
      indexingResult,
    }),
    [uploadedDocument, pipelineResult, indexingResult],
  );

  function handleAuthenticated(nextToken: string, nextUser: User) {
    setToken(nextToken);
    setUser(nextUser);
    localStorage.setItem(tokenStorageKey, nextToken);
    localStorage.setItem(userStorageKey, JSON.stringify(nextUser));
  }

  function handleLogout() {
    const confirmed = window.confirm("Logout now?");
    if (!confirmed) return;
    const currentUserId = user?.user_id;
    setToken("");
    setUser(null);
    setActiveView("chat");
    setMessages([]);
    setSessionId(null);
    setSessions([]);
    setUploadedDocument(null);
    setPipelineResult(null);
    setIndexingResult(null);
    localStorage.removeItem(tokenStorageKey);
    localStorage.removeItem(userStorageKey);
    if (currentUserId) {
      localStorage.removeItem(getDocumentStorageKey(currentUserId));
    }
  }

  if (!isConfigured || isEditingConfig) {
    return (
      <ConfigurationGate
        onConfigured={() => {
          setIsConfigured(true);
          setIsEditingConfig(false);
        }}
      />
    );
  }

  if (!token || !user) {
    return <AuthGate onAuthenticated={handleAuthenticated} />;
  }

  return (
    <AppShell
      activeView={activeView}
      user={user}
      serviceStatus={serviceStatus}
      sessions={sessions}
      activeSessionId={sessionId}
      onNavigate={(view) => {
        setActiveView(view);
        if (view === "documents") {
          void refreshDocuments().catch(() => undefined);
        }
      }}
      onNewChat={handleNewChat}
      onSelectSession={(nextSessionId) => void handleSelectSession(nextSessionId)}
      onDeleteSession={(targetSessionId) => void handleDeleteSession(targetSessionId)}
      onRefreshStatus={refreshStatus}
      isRefreshing={isRefreshing}
      onLogout={handleLogout}
    >
      {activeView === "chat" && (
        <ChatPage
          token={token}
          messages={messages}
          sessionId={sessionId}
          refreshRevision={refreshRevision}
          documentState={documentState}
          onMessagesChange={setMessages}
          onSessionChange={(nextSessionId) => {
            setSessionId(nextSessionId);
            refreshSessions().catch(() => undefined);
          }}
          onNewChat={handleNewChat}
          onUploadedDocument={setUploadedDocument}
          onPipelineResult={setPipelineResult}
          onIndexingResult={setIndexingResult}
        />
      )}
      {activeView === "documents" && (
        <DocumentsPage
          documents={documents}
          isLoading={isLoadingDocuments}
          deletingDocumentId={deletingDocumentId}
          onRefresh={() => {
            refreshDocuments().catch(() => undefined);
          }}
          onDelete={(document) => {
            void handleDeleteDocument(document);
          }}
        />
      )}
      {activeView === "settings" && (
        <SettingsPage
          user={user}
          onLogout={handleLogout}
          onRefreshStatus={refreshStatus}
          onEditConfiguration={() => setIsEditingConfig(true)}
        />
      )}
    </AppShell>
  );
}
