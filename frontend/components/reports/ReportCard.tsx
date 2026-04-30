"use client";
import type { AuditReportRecord } from "@/types/auditReport";

interface Props {
  report: AuditReportRecord;
}

export default function ReportCard({ report }: Props) {
  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm space-y-2">
      <div className="flex justify-between items-start">
        <h3 className="font-semibold text-sm">Shift {report.shift_id}</h3>
        <span className="text-xs text-gray-400">{report.generated_at}</span>
      </div>
      <p className="text-xs text-gray-400">Model: {report.model_used}</p>
      <pre className="text-sm whitespace-pre-wrap font-sans bg-gray-50 rounded p-3 max-h-64 overflow-y-auto">
        {report.report_text}
      </pre>
    </div>
  );
}
