export type StatusType = "online" | "offline" | "alert" | "shift-active" | "no-shift";

const CONFIG: Record<StatusType, { dot: string; text: string; label: string; pulse?: boolean }> = {
  "online":       { dot: "bg-s-success", text: "text-s-success", label: "ONLINE" },
  "offline":      { dot: "bg-s-muted",   text: "text-s-muted",   label: "OFFLINE" },
  "alert":        { dot: "bg-s-danger",  text: "text-s-danger",  label: "ALERT", pulse: true },
  "shift-active": { dot: "bg-s-accent",  text: "text-s-accent",  label: "SHIFT ACTIVE" },
  "no-shift":     { dot: "bg-s-muted",   text: "text-s-muted",   label: "NO ACTIVE SHIFT" },
};

export default function StatusBadge({ status }: { status: StatusType }) {
  const c = CONFIG[status];
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-s-elevated border border-s-border whitespace-nowrap shrink-0">
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot} ${c.pulse ? "animate-alert-pulse" : ""}`} />
      <span className={`font-mono text-[10px] font-medium tracking-widest ${c.text}`}>{c.label}</span>
    </span>
  );
}
