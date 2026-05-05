"use client";
import type { AlertRecord } from "@/types/alert";
import AlertTypeBadge from "@/components/shared/AlertTypeBadge";

interface Props { alert: AlertRecord; selected: boolean; onClick: () => void }

const CRITICAL = new Set(["man_down", "collision"]);

export default function AlertCard({ alert, selected, onClick }: Props) {
  const critical = CRITICAL.has(alert.alert_type) && !alert.resolved;

  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-lg border p-3 transition-all duration-150
        ${selected ? "border-s-accent bg-s-elevated" : "border-s-border bg-s-surface hover:bg-s-elevated"}
        ${critical ? "animate-alert-pulse" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <AlertTypeBadge type={alert.alert_type} />
        <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border
          ${alert.resolved
            ? "border-s-success text-s-success"
            : "border-s-danger text-s-danger"}`}>
          {alert.resolved ? "RESOLVED" : "ACTIVE"}
        </span>
      </div>
      <p className="text-xs text-s-text mt-2 font-medium">{alert.person_id}</p>
      <p className="text-xs text-s-muted">{alert.zone}</p>
      <p className="font-mono text-[10px] text-s-mono mt-1">{alert.timestamp}</p>
    </button>
  );
}
