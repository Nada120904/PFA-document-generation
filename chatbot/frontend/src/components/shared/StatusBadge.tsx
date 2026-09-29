type StatusBadgeProps = {
  label: string;
  tone?: "neutral" | "ok" | "warning" | "danger";
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  return <span className={`status-badge ${tone}`}>{label}</span>;
}
