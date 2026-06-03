"use client";
import { useState } from "react";
import type { AlertRecord, AlertType } from "@/types/alert";
import AlertCard from "./AlertCard";

type Filter = "all" | AlertType;

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all",              label: "All" },
  { value: "man_down",         label: "Man Down" },
  { value: "ghost_patrol",     label: "Ghost Patrol" },
  { value: "collision",        label: "Collision" },
  { value: "patrol_violation", label: "Patrol Breach" },
];

interface Props {
  alerts: AlertRecord[];
  selectedId: string | null;
  onSelectAlert: (alert: AlertRecord) => void;
  onDelete?: (id: string) => void;
  deletingId?: string | null;
}

export default function AlertList({ alerts, selectedId, onSelectAlert, onDelete, deletingId }: Props) {
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = filter === "all" ? alerts : alerts.filter((a) => a.alert_type === filter);

  return (
    <div className="flex flex-col h-full gap-3">
      {/* Filter bar */}
      <div className="flex gap-1 flex-wrap">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors
              ${filter === f.value
                ? "bg-s-accent text-s-base font-semibold"
                : "bg-s-elevated text-s-muted border border-s-border hover:text-s-text"}`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="divide-y divide-s-border/50">
          {filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center h-40 text-s-muted">
              <p className="text-sm">No alerts</p>
            </div>
          )}
          {filtered.map((a) => (
            <AlertCard
              key={a.alert_id}
              alert={a}
              selected={a.alert_id === selectedId}
              onClick={() => onSelectAlert(a)}
              onDelete={onDelete}
              deletingId={deletingId}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
