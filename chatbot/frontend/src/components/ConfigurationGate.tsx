import { FormEvent, useMemo, useState } from "react";
import { Bot, ChevronDown, Database, KeyRound, ServerCog, ShieldCheck } from "lucide-react";
import {
  loadRuntimeConfig,
  runtimeConfigSections,
  saveRuntimeConfig,
  type RuntimeConfigField,
  type RuntimeConfigSection,
  type RuntimeConfigValues,
} from "../lib/runtimeConfig";

type ConfigurationGateProps = {
  onConfigured: () => void;
};

const sectionIcons = {
  global: ShieldCheck,
  chatbot: Bot,
  upload: KeyRound,
  storage: Database,
  docling: FileCodeIcon,
  orchestration: ServerCog,
  lightrag: Database,
  vlm: ScanTextIcon,
} as const;

export function ConfigurationGate({ onConfigured }: ConfigurationGateProps) {
  const isDemoMode = import.meta.env.VITE_DEMO_MODE === "true";
  const [values, setValues] = useState<RuntimeConfigValues>(() => loadRuntimeConfig());
  const [openSection, setOpenSection] = useState("global");
  const [message, setMessage] = useState("");

  const filledCount = useMemo(
    () => Object.values(values).filter((value) => value.trim() !== "").length,
    [values],
  );

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    saveRuntimeConfig(values);
    setMessage("Configuration saved locally in this browser. Requests will now send these values as headers.");
    onConfigured();
  }

  function handleReset() {
    setValues({});
    setMessage("Configuration cleared from the form. Save again if you want to continue with empty values.");
  }

  function handleDemoContinue() {
    saveRuntimeConfig({ DEMO_MODE: "true" });
    onConfigured();
  }

  return (
    <main className="config-page">
      <section className="config-panel">
        <div className="brand-mark">
          <Bot size={28} aria-hidden="true" />
        </div>
        <div className="config-heading">
          <p className="eyebrow">RAG Workspace</p>
          <h1>Configure your workspace</h1>
          <p className="muted-text">
            {isDemoMode
              ? "Explore the document assistant using the local demo API. No external credentials are needed."
              : "Configure runtime values for the deployed core engine."}
          </p>
        </div>

        {isDemoMode && (
          <div className="note-box">
            <p>The local demo stores sample data on this computer. Production services and external storage are not started.</p>
            <button className="primary-button" type="button" onClick={handleDemoContinue}>
              Continue to local demo
            </button>
          </div>
        )}

        {!isDemoMode && <><div className="config-summary-row">
          <div className="status-summary">
            <Database size={16} aria-hidden="true" />
            <span>{filledCount} values filled</span>
          </div>
          <button className="secondary-button" type="button" onClick={handleReset}>
            Clear form
          </button>
        </div>

        <div className="note-box">
          Values on this page stay in this browser and are attached to API requests as runtime headers. Keep API keys and
          database passwords in server configuration instead.
        </div>

        <form className="config-form" onSubmit={handleSubmit}>
          {runtimeConfigSections.map((section) => (
            <ConfigSectionCard
              key={section.key}
              section={section}
              isOpen={openSection === section.key}
              values={values}
              onToggle={() => setOpenSection(openSection === section.key ? "" : section.key)}
              onChange={(fieldKey, nextValue) =>
                setValues((previous) => ({
                  ...previous,
                  [fieldKey]: nextValue,
                }))
              }
            />
          ))}

          {message && <div className="notice-banner">{message}</div>}

          <div className="config-actions">
            <button className="primary-button" type="submit">
              Save and continue
            </button>
          </div>
        </form></>}
      </section>
    </main>
  );
}

type ConfigSectionCardProps = {
  section: RuntimeConfigSection;
  isOpen: boolean;
  values: RuntimeConfigValues;
  onToggle: () => void;
  onChange: (fieldKey: string, value: string) => void;
};

function ConfigSectionCard({ section, isOpen, values, onToggle, onChange }: ConfigSectionCardProps) {
  const Icon = sectionIcons[section.key as keyof typeof sectionIcons] || ServerCog;
  const filledFields = section.fields.filter((field) => (values[field.key] || "").trim() !== "").length;

  return (
    <article className={isOpen ? "config-section open" : "config-section"}>
      <button className="service-panel-trigger" type="button" onClick={onToggle}>
        <div className="service-panel-title">
          <div className="panel-icon">
            <Icon size={20} aria-hidden="true" />
          </div>
          <div>
            <h3>{section.title}</h3>
            <p>{section.description}</p>
          </div>
        </div>
        <div className="service-panel-meta">
          <span className="status-badge">{filledFields}/{section.fields.length} filled</span>
          <ChevronDown size={18} aria-hidden="true" />
        </div>
      </button>
      {isOpen && (
        <div className="config-section-body">
          <div className="config-grid">
            {section.fields.map((field) => (
              <ConfigField
                key={field.key}
                field={field}
                value={values[field.key] || ""}
                onChange={(nextValue) => onChange(field.key, nextValue)}
              />
            ))}
          </div>
        </div>
      )}
    </article>
  );
}

function ConfigField({
  field,
  value,
  onChange,
}: {
  field: RuntimeConfigField;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field">
      <span>{field.label}</span>
      {field.multiline ? (
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder}
          rows={4}
        />
      ) : (
        <input
          type={field.type || "text"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder}
        />
      )}
    </label>
  );
}

function FileCodeIcon({ size = 20 }: { size?: number }) {
  return <ServerCog size={size} aria-hidden="true" />;
}

function ScanTextIcon({ size = 20 }: { size?: number }) {
  return <KeyRound size={size} aria-hidden="true" />;
}
