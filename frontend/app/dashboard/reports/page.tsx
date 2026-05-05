"use client";
import { useEffect, useState } from "react";
import { subscribeToReports, unsubscribeFromReports, generateReport } from "@/services/reportService";
import { getDistinctShifts, type ShiftOption } from "@/services/patrolLogService";
import type { AuditReportRecord } from "@/types/auditReport";
import ReportCard from "@/components/reports/ReportCard";
import { toast } from "@/store/toastStore";

function SimpleMarkdown({ text }: { text: string }) {
  return (
    <div className="space-y-1.5 text-sm text-s-text leading-relaxed">
      {text.split("\n").map((line, i) => {
        if (line.startsWith("## "))
          return <h2 key={i} className="font-bold text-s-accent font-mono text-xs tracking-widest uppercase mt-4 mb-1">{line.slice(3)}</h2>;
        if (line.startsWith("### "))
          return <h3 key={i} className="font-semibold text-s-text text-xs mt-3 mb-0.5">{line.slice(4)}</h3>;
        if (line.startsWith("- ") || line.startsWith("* "))
          return <li key={i} className="ml-4 list-disc text-s-muted text-xs">{line.slice(2)}</li>;
        if (line.trim() === "")
          return <div key={i} className="h-1" />;
        return <p key={i} className="text-xs text-s-muted">{line}</p>;
      })}
    </div>
  );
}

export default function ReportsPage() {
  const [reports, setReports] = useState<AuditReportRecord[]>([]);
  const [selected, setSelected] = useState<AuditReportRecord | null>(null);
  const [shifts, setShifts] = useState<ShiftOption[]>([]);
  const [shiftId, setShiftId] = useState("");
  const [generating, setGenerating] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    subscribeToReports((data) => setReports(data));
    getDistinctShifts().then(setShifts).catch(() => {});
    return () => unsubscribeFromReports();
  }, []);

  async function handleGenerate() {
    if (!shiftId.trim()) return;
    setGenerating(true);
    try {
      await generateReport({ shift_id: shiftId.trim(), patrol_summaries: [], alert_summaries: [] });
      toast.success("Report generated successfully");
    } catch {
      toast.error("Failed to generate report");
    } finally {
      setGenerating(false);
    }
  }

  async function handleCopy() {
    if (!selected?.report_text) return;
    await navigator.clipboard.writeText(selected.report_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-5rem)] max-w-[1600px]">
      {/* Left — report list (35%) */}
      <div className="w-[35%] flex flex-col min-w-0 gap-3">
        <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">
          Audit Reports ({reports.length})
        </h1>

        {/* Shift selector + generate */}
        <div className="flex gap-2">
          {shifts.length > 0 ? (
            <select
              value={shiftId}
              onChange={(e) => setShiftId(e.target.value)}
              className="flex-1 bg-s-surface border border-s-border rounded-lg px-3 py-2 text-xs text-s-text font-mono focus:outline-none focus:border-s-accent"
            >
              <option value="">Select shift…</option>
              {shifts.map((s) => (
                <option key={s.shift_id} value={s.shift_id}>
                  {s.shift_id} · {s.guard_id} · {s.date}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={shiftId}
              onChange={(e) => setShiftId(e.target.value)}
              placeholder="Enter shift ID…"
              className="flex-1 bg-s-surface border border-s-border rounded-lg px-3 py-2 text-xs text-s-text font-mono placeholder:text-s-muted focus:outline-none focus:border-s-accent"
            />
          )}
          <button
            onClick={handleGenerate}
            disabled={!shiftId.trim() || generating}
            className="px-3 py-2 bg-s-accent text-s-base rounded-lg text-xs font-bold font-mono disabled:opacity-40 hover:opacity-90 transition-opacity flex items-center gap-1.5 whitespace-nowrap"
          >
            {generating && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
            {generating ? "Generating…" : "Generate"}
          </button>
        </div>

        {/* Report list */}
        <div className="flex-1 overflow-y-auto space-y-2 pr-1">
          {reports.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 gap-2">
              <p className="text-s-muted text-xs font-mono">No reports yet</p>
            </div>
          ) : (
            reports.map((r) => (
              <ReportCard
                key={r.report_id}
                report={r}
                selected={selected?.report_id === r.report_id}
                onClick={() => setSelected(r)}
              />
            ))
          )}
        </div>
      </div>

      {/* Right — detail panel (65%) */}
      <div className="flex-1 min-w-0 flex flex-col">
        {selected ? (
          <div className="flex flex-col h-full bg-s-surface border border-s-border rounded-lg overflow-hidden">
            {/* Header */}
            <div className="flex items-start justify-between p-4 border-b border-s-border">
              <div>
                <p className="font-mono text-xs text-s-accent tracking-widest">Shift {selected.shift_id}</p>
                <p className="font-mono text-[10px] text-s-muted mt-0.5">{selected.generated_at}</p>
                <p className="font-mono text-[10px] text-s-muted">{selected.model_used}</p>
              </div>
              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-s-border bg-s-elevated text-xs font-mono text-s-muted hover:text-s-text hover:border-s-accent transition-colors"
              >
                {copied ? (
                  <>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                    Copied
                  </>
                ) : (
                  <>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                    </svg>
                    Copy
                  </>
                )}
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-4">
              {selected.report_text ? (
                <SimpleMarkdown text={selected.report_text} />
              ) : (
                <p className="text-s-muted text-xs font-mono">No report content.</p>
              )}
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center bg-s-surface border border-s-border rounded-lg text-center gap-3">
            <svg className="text-s-muted" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
              <polyline points="10 9 9 9 8 9"/>
            </svg>
            <p className="text-s-text font-medium">No Report Selected</p>
            <p className="text-s-muted text-sm">Select a report to view its contents</p>
          </div>
        )}
      </div>
    </div>
  );
}
