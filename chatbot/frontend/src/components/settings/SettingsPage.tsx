import { LogOut, Pencil, RefreshCw, Server } from "lucide-react";
import { apiConfig } from "../../lib/api";
import type { User } from "../../types";

type SettingsPageProps = {
  user: User;
  onLogout: () => void;
  onRefreshStatus: () => Promise<void>;
  onEditConfiguration: () => void;
};

export function SettingsPage({ user, onLogout, onRefreshStatus, onEditConfiguration }: SettingsPageProps) {
  return (
    <section className="content-grid two-columns settings-grid">
      <article className="surface settings-surface">
        <div className="surface-header">
          <div>
            <p className="eyebrow">Account</p>
            <h2>Current user</h2>
          </div>
        </div>
        <div className="info-list settings-info-list">
          <div>
            <span>Name</span>
            <strong>{user.name}</strong>
          </div>
          <div>
            <span>Email</span>
            <strong>{user.email}</strong>
          </div>
        </div>
        <div className="settings-actions">
          <button className="secondary-button" type="button" onClick={onLogout}>
            <LogOut size={16} aria-hidden="true" />
            Logout
          </button>
        </div>
      </article>

      <article className="surface settings-surface">
        <div className="surface-header">
          <div>
            <p className="eyebrow">API</p>
            <h2>Frontend configuration</h2>
          </div>
          <Server size={20} aria-hidden="true" />
        </div>
        <div className="info-list settings-info-list">
          <div>
            <span>Chatbot backend</span>
            <strong>{apiConfig.chatbotBaseUrl}</strong>
          </div>
          <div>
            <span>Orchestration service</span>
            <strong>{apiConfig.orchestrationBaseUrl}</strong>
          </div>
        </div>
        <div className="settings-actions">
          <button className="secondary-button" type="button" onClick={onEditConfiguration}>
            <Pencil size={16} aria-hidden="true" />
            Edit runtime configuration
          </button>
          <button className="secondary-button" type="button" onClick={() => void onRefreshStatus()}>
            <RefreshCw size={16} aria-hidden="true" />
            Refresh service status
          </button>
        </div>
      </article>
    </section>
  );
}
