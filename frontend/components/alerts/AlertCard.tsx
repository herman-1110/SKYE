"use client";
import type { AlertRecord } from "@/types/alert";
import StatusBadge from "@/components/shared/StatusBadge";

interface Props {
  alert: AlertRecord;
  onClick: () => void;
}

const LABELS: Record<string, string> = {
  man_down:         "Man Down",
  collision:        "Collision Risk",
  ghost_patrol:     "Ghost Patrol",
  patrol_violation: "Patrol Violation",
};

export default function AlertCard({ alert, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-lg border p-3 hover:bg-gray-50 transition-colors"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-sm">
          {LABELS[alert.alert_type] ?? alert.alert_type}
        </span>
        <StatusBadge status={alert.resolved ? "offline" : "alert"} />
      </div>
      <p className="text-xs text-gray-500 mt-1">
        {alert.person_id} · {alert.zone}
      </p>
      <p className="text-xs text-gray-400 mt-0.5">{alert.timestamp}</p>
    </button>
  );
}
