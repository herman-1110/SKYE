"use client";
import type { AuditReportRecord } from "@/types/auditReport";

interface Props { report: AuditReportRecord; selected: boolean; onClick: () => void }

export default function ReportCard({ report, selected, onClick }: Props) {
  const preview = report.report_text?.slice(0, 80) ?? "";

  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-lg border p-3 transition-all
        ${selected ? "border-s-accent bg-s-elevated" : "border-s-border bg-s-surface hover:bg-s-elevated"}`}
    >
      <p className="font-mono text-xs text-s-accent">Shift {report.shift_id}</p>
      <p className="font-mono text-[10px] text-s-muted mt-0.5">{report.generated_at}</p>
      <p className="font-mono text-[10px] text-s-mono mt-1 truncate">{report.model_used}</p>
      <p className="text-xs text-s-muted mt-2 line-clamp-2">{preview}…</p>
    </button>
  );
}
