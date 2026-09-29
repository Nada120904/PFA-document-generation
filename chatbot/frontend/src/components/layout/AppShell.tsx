import {
  Bot,
  ChevronUp,
  Database,
  Files,
  LogOut,
  Loader2,
  Plus,
  RefreshCw,
  Settings,
  Trash2,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import type { ChatSession, ServiceStatusResponse, User, ViewKey } from "../../types";

type AppShellProps = {
  activeView: ViewKey;
  user: User;
  serviceStatus: ServiceStatusResponse | null;
  sessions: ChatSession[];
  activeSessionId: string | null;
  children: ReactNode;
  onNavigate: (view: ViewKey) => void;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onRefreshStatus: () => Promise<void>;
  isRefreshing: boolean;
  onLogout: () => void;
};

const navItems: Array<{ key: ViewKey; label: string; icon: typeof Bot }> = [
  { key: "chat", label: "Chatbot", icon: Bot },
  { key: "documents", label: "Documents", icon: Files },
  { key: "settings", label: "Settings", icon: Settings },
];

export function AppShell({
  activeView,
  user,
  serviceStatus,
  sessions,
  activeSessionId,
  children,
  onNavigate,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onRefreshStatus,
  isRefreshing,
  onLogout,
}: AppShellProps) {
  const isDemoMode = import.meta.env.VITE_DEMO_MODE === "true";
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const reachableCount = serviceStatus
    ? Object.values(serviceStatus).filter((service) => service.reachable).length
    : 0;
  const serviceCount = serviceStatus ? Object.values(serviceStatus).length : 0;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark small">
            <Bot size={22} aria-hidden="true" />
          </div>
          <div>
            <strong>RAG Chatbot</strong>
            <span>Document assistant</span>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Primary navigation">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                className={activeView === item.key ? "nav-item active" : "nav-item"}
                type="button"
                onClick={() => onNavigate(item.key)}
              >
                <Icon size={18} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <section className="session-list" aria-label="Chat sessions">
          <div className="session-list-header">
            <span>Chat sessions</span>
          </div>
          <button className="session-new-button" type="button" onClick={onNewChat}>
            <Plus size={15} aria-hidden="true" />
            New chat
          </button>
          <div className="session-items">
            {sessions.length === 0 && <p className="session-empty">No saved sessions yet</p>}
            {sessions.map((session, index) => (
              <div
                key={session.session_id}
                className={activeSessionId === session.session_id ? "session-item active" : "session-item"}
              >
                <button
                  className="session-item-main"
                  type="button"
                  onClick={() => onSelectSession(session.session_id)}
                >
                  <span>{session.title || `Session ${index + 1}`}</span>
                </button>
                <button
                  className="session-delete-button"
                  type="button"
                  title="Delete chat"
                  aria-label={`Delete ${session.title || `session ${index + 1}`}`}
                  onClick={() => onDeleteSession(session.session_id)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
        </section>

        <div className="sidebar-footer">
          <button
            className={`user-menu-trigger${isUserMenuOpen ? " open" : ""}`}
            type="button"
            onClick={() => setIsUserMenuOpen((previous) => !previous)}
          >
            <div className="user-mini">
              <div className="avatar">{user.name.slice(0, 1).toUpperCase()}</div>
              <div>
                <strong>{user.name}</strong>
                <span>{user.email}</span>
              </div>
            </div>
            <ChevronUp size={16} aria-hidden="true" className={isUserMenuOpen ? "rotate-icon" : ""} />
          </button>
          {isUserMenuOpen && (
            <div className="user-menu-actions">
              <button
                className="icon-text-button"
                type="button"
                onClick={() => {
                  onNavigate("settings");
                  setIsUserMenuOpen(false);
                }}
              >
                <Settings size={16} aria-hidden="true" />
                Settings
              </button>
              <button
                className="icon-text-button"
                type="button"
                onClick={() => {
                  setIsUserMenuOpen(false);
                  onLogout();
                }}
              >
                <LogOut size={16} aria-hidden="true" />
                Logout
              </button>
            </div>
          )}
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Enterprise workspace</p>
            <h1>{navItems.find((item) => item.key === activeView)?.label}</h1>
          </div>
          <div className="topbar-actions">
            <div className="status-summary">
              <Database size={16} aria-hidden="true" />
              <span>
                {isDemoMode
                  ? serviceStatus?.orchestration?.reachable
                    ? "Local demo API online"
                    : "Local demo API unavailable"
                  : serviceStatus
                    ? `${reachableCount}/${serviceCount} services online`
                    : "Status not loaded"}
              </span>
            </div>
            <button className="secondary-button" type="button" onClick={() => void onRefreshStatus()} disabled={isRefreshing}>
              {isRefreshing ? <Loader2 size={16} aria-hidden="true" className="spin-icon" /> : <RefreshCw size={16} aria-hidden="true" />}
              {isRefreshing ? "Refreshing" : "Refresh"}
            </button>
          </div>
        </header>
        <main className="workspace-content">{children}</main>
      </div>
    </div>
  );
}
