"use client";
import React, { useEffect, useState } from "react";
import {
  subscribeToReports,
  unsubscribeFromReports,
  generateReport,
  fetchReportableShifts,
  fetchSafetyEventGroups,
  generateSafetyReport,
  type ReportableShift,
  type SafetyEventGroup,
} from "@/services/reportService";
import type { AuditReportRecord } from "@/types/auditReport";
import ReportCard from "@/components/reports/ReportCard";
import { toast } from "@/store/toastStore";
import { useDashboardStore } from "@/store/dashboardStore";

function inlineParse(line: string): React.ReactNode {
  const parts = line.split("**");
  return parts.map((part, i) =>
    i % 2 === 1
      ? <strong key={i} className="font-semibold text-s-text">{part}</strong>
      : <span key={i}>{part}</span>
  );
}

function SimpleMarkdown({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm text-s-text leading-relaxed">
      {text.split("\n").map((line, i) => {
        if (line.startsWith("# "))
          return (
            <h1 key={i} className="font-bold text-s-text text-lg mt-4 mb-2 leading-snug">
              {inlineParse(line.slice(2))}
            </h1>
          );
        if (line.startsWith("## "))
          return (
            <h2 key={i} className="font-bold text-s-accent font-mono text-xs tracking-widest uppercase mt-5 mb-2 border-b border-s-border pb-1">
              {line.slice(3)}
            </h2>
          );
        if (line.startsWith("### "))
          return (
            <h3 key={i} className="font-semibold text-s-text text-sm mt-3 mb-1">
              {inlineParse(line.slice(4))}
            </h3>
          );
        if (line.trim() === "---")
          return <hr key={i} className="border-s-border my-3" />;
        if (line.startsWith("- ") || line.startsWith("* "))
          return (
            <li key={i} className="ml-5 list-disc text-s-text text-sm leading-relaxed">
              {inlineParse(line.slice(2))}
            </li>
          );
        if (/^\d+\.\s/.test(line))
          return (
            <p key={i} className="ml-2 text-s-text text-sm leading-relaxed">
              {inlineParse(line)}
            </p>
          );
        if (line.trim() === "")
          return <div key={i} className="h-2" />;
        return (
          <p key={i} className="text-s-text text-sm leading-relaxed">
            {inlineParse(line)}
          </p>
        );
      })}
    </div>
  );
}

type Tab = "patrol" | "events";

export default function ReportsPage() {
  const { cachedReports, setCachedReports } = useDashboardStore();
  const [reports, setReports] = useState<AuditReportRecord[]>(cachedReports);
  const [selected, setSelected] = useState<AuditReportRecord | null>(null);
  const [shifts, setShifts] = useState<ReportableShift[]>([]);
  const [selectedShift, setSelectedShift] = useState<ReportableShift | null>(null);
  const [loadingShifts, setLoadingShifts] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isLoading, setIsLoading] = useState(cachedReports.length === 0);
  const [tab, setTab] = useState<Tab>("patrol");

  const [safetyGroups, setSafetyGroups] = useState<SafetyEventGroup[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<SafetyEventGroup | null>(null);
  const [loadingSafetyGroups, setLoadingSafetyGroups] = useState(false);
  const [generatingSafety, setGeneratingSafety] = useState(false);
  const [selectedSafetyReport, setSelectedSafetyReport] = useState<AuditReportRecord | null>(null);

  const patrolReports = reports.filter((r) => !r.report_type || r.report_type === "patrol");
  const safetyReports = reports.filter((r) => r.report_type === "safety_event");

  useEffect(() => {
    subscribeToReports((data) => {
      setReports(data);
      setCachedReports(data);
      setIsLoading(false);
    });
    setLoadingShifts(true);
    fetchReportableShifts().then(setShifts).catch(() => {}).finally(() => setLoadingShifts(false));
    setLoadingSafetyGroups(true);
    fetchSafetyEventGroups().then(setSafetyGroups).catch(() => {}).finally(() => setLoadingSafetyGroups(false));
    return () => unsubscribeFromReports();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleGenerate() {
    if (!selectedShift) return;
    setGenerating(true);
    try {
      await generateReport({ log_id: selectedShift.log_id, guard_id: selectedShift.guard_id });
      toast.success("Report generated successfully");
    } catch {
      toast.error("Failed to generate report");
    } finally {
      setGenerating(false);
    }
  }

  async function handleGenerateSafety() {
    if (!selectedGroup) return;
    setGeneratingSafety(true);
    try {
      await generateSafetyReport({
        person_id: selectedGroup.person_id,
        date_str: selectedGroup.date_str,
      });
      toast.success("Safety report generated");
    } catch {
      toast.error("Failed to generate safety report");
    } finally {
      setGeneratingSafety(false);
    }
  }

  if (isLoading) return (
    <div className="flex gap-4 h-[calc(100vh-5rem)] max-w-[1600px]">
      <div className="w-[35%] flex flex-col gap-3">
        <div className="h-3 bg-s-elevated rounded w-28 animate-pulse" />
        <div className="h-9 bg-s-elevated rounded animate-pulse" />
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bento-card animate-pulse">
            <div className="h-4 bg-s-elevated rounded w-3/4 mb-2" />
            <div className="h-3 bg-s-elevated rounded w-1/2" />
          </div>
        ))}
      </div>
      <div className="flex-1 bg-s-elevated rounded-xl animate-pulse" />
    </div>
  );

  return (
    <div className="flex gap-4 h-[calc(100vh-5rem)] max-w-[1600px]">
      {/* Left panel */}
      <div className="w-[35%] flex flex-col min-w-0 gap-3">
        {/* Tab switcher */}
        <div className="flex gap-1">
          {(["patrol", "events"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded-md text-xs font-mono transition-colors ${
                tab === t
                  ? "bg-s-accent text-s-base font-semibold"
                  : "bg-s-elevated text-s-muted border border-s-border hover:text-s-text"
              }`}
            >
              {t === "patrol" ? "Patrol Reports" : "Safety Events"}
            </button>
          ))}
        </div>

        {tab === "patrol" ? (
          <>
            <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">
              Audit Reports ({patrolReports.length})
            </h1>

            {/* Shift selector + generate */}
            <div className="flex gap-2">
              {loadingShifts ? (
                <p className="flex-1 text-s-muted text-xs font-mono px-3 py-2">Loading shifts…</p>
              ) : shifts.length === 0 ? (
                <p className="flex-1 text-s-muted text-xs font-mono px-3 py-2">No completed patrol shifts available. Run a simulation first.</p>
              ) : (
                <select
                  value={selectedShift ? `${selectedShift.log_id}|${selectedShift.guard_id}` : ""}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (!val) { setSelectedShift(null); return; }
                    const sep = val.indexOf("|");
                    const logId = val.slice(0, sep);
                    const guardId = val.slice(sep + 1);
                    setSelectedShift(shifts.find((s) => s.log_id === logId && s.guard_id === guardId) ?? null);
                  }}
                  className="flex-1 bg-s-surface border border-s-border rounded-lg px-3 py-2 text-xs text-s-text font-mono focus:outline-none focus:border-s-accent"
                >
                  <option value="">Select a shift…</option>
                  {shifts.map((s) => {
                    const start = s.shift_start
                      ? new Date(s.shift_start * 1000).toLocaleString()
                      : "Unknown start";
                    return (
                      <option key={`${s.log_id}|${s.guard_id}`} value={`${s.log_id}|${s.guard_id}`}>
                        {s.guard_label} — {start}
                      </option>
                    );
                  })}
                </select>
              )}
              <button
                onClick={handleGenerate}
                disabled={!selectedShift || generating}
                className="px-3 py-2 bg-s-accent text-s-base rounded-lg text-xs font-bold font-mono disabled:opacity-40 hover:opacity-90 transition-opacity flex items-center gap-1.5 whitespace-nowrap"
              >
                {generating && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
                {generating ? "Generating…" : "Generate"}
              </button>
            </div>

            {/* Patrol report list */}
            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {patrolReports.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 gap-2">
                  <p className="text-s-muted text-xs font-mono">No reports yet</p>
                </div>
              ) : (
                patrolReports.map((r) => (
                  <ReportCard
                    key={r.report_id}
                    report={r}
                    selected={selected?.report_id === r.report_id}
                    onClick={() => setSelected(r)}
                  />
                ))
              )}
            </div>
          </>
        ) : (
          <>
            <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">
              Safety Reports ({safetyReports.length})
            </h1>

            {/* Person+date selector + generate */}
            <div className="flex gap-2">
              {loadingSafetyGroups ? (
                <p className="flex-1 text-s-muted text-xs font-mono px-3 py-2">
                  Loading…
                </p>
              ) : safetyGroups.length === 0 ? (
                <p className="flex-1 text-s-muted text-xs font-mono px-3 py-2">
                  No safety alerts recorded yet.
                </p>
              ) : (
                <select
                  value={
                    selectedGroup
                      ? `${selectedGroup.person_id}|${selectedGroup.date_str}`
                      : ""
                  }
                  onChange={(e) => {
                    const val = e.target.value;
                    if (!val) { setSelectedGroup(null); return; }
                    const [personId, dateStr] = val.split("|");
                    setSelectedGroup(
                      safetyGroups.find(
                        (g) => g.person_id === personId && g.date_str === dateStr
                      ) ?? null
                    );
                  }}
                  className="flex-1 bg-s-surface border border-s-border rounded-lg px-3 py-2 text-xs text-s-text font-mono focus:outline-none focus:border-s-accent"
                >
                  <option value="">Select person + date…</option>
                  {safetyGroups.map((g) => (
                    <option
                      key={`${g.person_id}|${g.date_str}`}
                      value={`${g.person_id}|${g.date_str}`}
                    >
                      {g.person_id} — {g.date_str} ({g.alert_count} alert
                      {g.alert_count !== 1 ? "s" : ""})
                    </option>
                  ))}
                </select>
              )}
              <button
                onClick={handleGenerateSafety}
                disabled={!selectedGroup || generatingSafety}
                className="px-3 py-2 bg-s-accent text-s-base rounded-lg text-xs font-bold font-mono disabled:opacity-40 hover:opacity-90 transition-opacity flex items-center gap-1.5 whitespace-nowrap"
              >
                {generatingSafety && (
                  <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />
                )}
                {generatingSafety ? "Generating…" : "Generate"}
              </button>
            </div>

            {/* Safety report list */}
            <div className="flex-1 overflow-y-auto space-y-2 pr-1">
              {safetyReports.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 gap-2">
                  <p className="text-s-muted text-xs font-mono">No safety reports yet</p>
                </div>
              ) : (
                safetyReports.map((r) => (
                  <ReportCard
                    key={r.report_id}
                    report={r}
                    selected={selectedSafetyReport?.report_id === r.report_id}
                    onClick={() => setSelectedSafetyReport(r)}
                  />
                ))
              )}
            </div>
          </>
        )}
      </div>

      {/* Right — detail panel (both tabs) */}
      <div className="flex-1 min-w-0 flex flex-col">
        {(() => {
          const active = tab === "patrol" ? selected : selectedSafetyReport;
          if (!active) return (
            <div className="h-full flex flex-col items-center justify-center text-center gap-3">
              <svg className="text-s-muted" width="40" height="40" viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth="1.5"
                strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
                <polyline points="10 9 9 9 8 9"/>
              </svg>
              <p className="text-s-text font-medium">No Report Selected</p>
              <p className="text-s-muted text-sm">Select a report to view its contents</p>
            </div>
          );
          return (
            <div className="flex flex-col h-full bg-s-surface border border-s-border rounded-lg overflow-hidden">
              <div className="flex items-start justify-between p-4 border-b border-s-border">
                <div>
                  <p className="font-mono text-sm text-s-accent tracking-widest font-semibold">
                    {active.shift_id}
                  </p>
                  {active.guard_id && (
                    <p className="font-mono text-xs text-s-muted mt-0.5">
                      {active.report_type === "safety_event" ? "Person" : "Guard"}: {active.guard_id}
                    </p>
                  )}
                  <p className="font-mono text-xs text-s-muted mt-0.5">
                    {active.generated_at}
                  </p>
                  <p className="font-mono text-xs text-s-muted">
                    {active.model_used}
                  </p>
                </div>
                <button
                  onClick={() => {
                    if (!active?.report_text) return;
                    navigator.clipboard.writeText(active.report_text);
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-s-border bg-s-elevated text-xs font-mono text-s-muted hover:text-s-text hover:border-s-accent transition-colors"
                >
                  {copied ? (
                    <>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" strokeWidth="2"
                        strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12"/>
                      </svg>
                      Copied
                    </>
                  ) : (
                    <>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" strokeWidth="2"
                        strokeLinecap="round" strokeLinejoin="round">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                      </svg>
                      Copy
                    </>
                  )}
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                {active.report_text ? (
                  <SimpleMarkdown text={active.report_text} />
                ) : (
                  <p className="text-s-muted text-xs font-mono">No report content.</p>
                )}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}
