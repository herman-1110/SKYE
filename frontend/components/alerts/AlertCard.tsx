"use client";
import type { AlertRecord } from "@/types/alert";
import AlertTypeBadge from "@/components/shared/AlertTypeBadge";

interface Props {
  alert: AlertRecord;
  selected: boolean;
  onClick: () => void;
  onDelete?: (id: string) => void;
  deletingId?: string | null;
}

const CRITICAL = new Set(["man_down", "collision"]);

export default function AlertCard({ alert, selected, onClick, onDelete, deletingId }: Props) {
  const critical = CRITICAL.has(alert.alert_type) && !alert.resolved;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
      className={`relative w-full text-left px-4 py-3 transition-colors cursor-pointer
        ${selected ? "bg-s-elevated" : "hover:bg-s-elevated/60"}`}
    >
      {/* Left indicator */}
      {selected && <span className="absolute left-0 top-0 bottom-0 w-0.5 bg-s-accent" />}
      {!selected && critical && <span className="absolute left-0 top-0 bottom-0 w-0.5 bg-s-danger animate-amber-pulse" />}

      <div className="flex items-start justify-between gap-2">
        <AlertTypeBadge type={alert.alert_type} />
        <span className={`shrink-0 text-[10px] font-mono px-2 py-0.5 rounded-full border
          ${alert.resolved
            ? "border-s-success text-s-success"
            : "border-s-danger text-s-danger"}`}>
          {alert.resolved ? "RESOLVED" : "ACTIVE"}
        </span>
      </div>
      <p className="text-xs text-s-text mt-1.5 font-medium">{alert.person_id}</p>
      {alert.alert_type === "collision" && alert.other_person_id && (
        <p className="text-xs text-s-muted font-medium">
          ↔ {alert.other_person_id}
        </p>
      )}
      <p className="text-xs text-s-muted">{alert.zone}</p>
      <p className="font-mono text-[10px] text-s-mono mt-1">{alert.timestamp}</p>

      {alert.resolved && onDelete && (
        <div className="mt-2 flex justify-end">
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(alert.alert_id); }}
            disabled={deletingId === alert.alert_id}
            className="px-2.5 py-1 rounded-md text-[11px] font-mono border border-s-danger text-s-danger bg-transparent hover:bg-s-danger/10 transition-colors disabled:opacity-50"
          >
            {deletingId === alert.alert_id ? "Removing…" : "Remove"}
          </button>
        </div>
      )}
    </div>
  );
}
