"use client";
import { useState } from "react";
import { useDashboardStore } from "@/store/dashboardStore";
import AlertList from "@/components/alerts/AlertList";
import FeedbackForm from "@/components/alerts/FeedbackForm";
import { deleteAlert } from "@/services/alertService";
import type { AlertRecord } from "@/types/alert";

export default function AlertsPage() {
  const alerts = useDashboardStore((s) => s.alerts);
  const [selected, setSelected] = useState<AlertRecord | null>(null);
  const [tab, setTab] = useState<"active" | "resolved">("active");
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const alertList = Object.values(alerts) as AlertRecord[];

  const filtered = alertList
    .filter((a) => (tab === "active" ? !a.resolved : a.resolved))
    .filter((a) => {
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        a.alert_type?.toLowerCase().includes(q) ||
        a.zone?.toLowerCase().includes(q) ||
        a.person_id?.toLowerCase().includes(q)
      );
    });

  const activeCount   = alertList.filter((a) => !a.resolved).length;
  const resolvedCount = alertList.filter((a) =>  a.resolved).length;

  async function handleDelete(alertId: string) {
    setDeletingId(alertId);
    try {
      await deleteAlert(alertId);
      if (selected?.alert_id === alertId) setSelected(null);
    } catch (err) {
      console.error("Failed to delete alert", err);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-5rem)] max-w-[1600px]">
      {/* Left — alert list (40%) */}
      <div className="w-[40%] flex flex-col min-w-0 gap-3">

        {/* Search */}
        <div className="relative">
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            className="absolute left-2.5 top-1/2 -translate-y-1/2 text-s-muted pointer-events-none"
          >
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            placeholder="Search alerts…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-2 rounded-lg border border-s-border bg-s-surface text-s-text text-sm placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
          />
        </div>

        {/* Tabs */}
        <div className="flex gap-2">
          {(["active", "resolved"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full border text-xs font-mono transition-colors
                ${tab === t
                  ? "bg-s-accent text-s-base border-s-accent font-semibold"
                  : "bg-s-surface text-s-muted border-s-border hover:text-s-text"}`}
            >
              {t === "active" ? "Active" : "Resolved"}
              <span className={`px-1.5 py-0.5 rounded-full text-[10px]
                ${tab === t ? "bg-black/15" : "bg-s-elevated"}`}>
                {t === "active" ? activeCount : resolvedCount}
              </span>
            </button>
          ))}
        </div>

        {/* List */}
        <div className="flex-1 overflow-hidden">
          <AlertList
            alerts={filtered}
            selectedId={selected?.alert_id ?? null}
            onSelectAlert={setSelected}
            onDelete={handleDelete}
            deletingId={deletingId}
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
          <div className="h-full flex flex-col items-center justify-center text-center gap-3">
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
