"use client";
import { useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import AlertList from "@/components/alerts/AlertList";
import FeedbackForm from "@/components/alerts/FeedbackForm";
import type { AlertRecord } from "@/types/alert";

export default function AlertsPage() {
  const alerts = useDashboardStore((s) => s.alerts);
  const [selected, setSelected] = useState<AlertRecord | null>(null);
  const alertList = Object.values(alerts) as AlertRecord[];

  return (
    <div className="flex gap-4 h-[calc(100vh-5rem)] max-w-[1600px]">
      {/* Left — alert list (40%) */}
      <div className="w-[40%] flex flex-col min-w-0">
        <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase mb-3">
          All Alerts ({alertList.length})
        </h1>
        <div className="flex-1 overflow-hidden">
          <AlertList
            alerts={alertList}
            selectedId={selected?.alert_id ?? null}
            onSelectAlert={setSelected}
          />
        </div>
      </div>

      {/* Right — feedback panel (60%) */}
      <div className="flex-1 min-w-0">
        {selected ? (
          <FeedbackForm
            alert={selected}
            onSubmitted={() => setSelected(null)}
          />
        ) : (
          <div className="h-full flex flex-col items-center justify-center bg-s-surface border border-s-border rounded-lg text-center gap-3">
            <svg className="text-s-muted" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
              <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
            </svg>
            <p className="text-s-text font-medium">No Alert Selected</p>
            <p className="text-s-muted text-sm">Select an alert to review and respond</p>
          </div>
        )}
      </div>
    </div>
  );
}
