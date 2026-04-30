"use client";
import { useState } from "react";
import { generateReport } from "@/services/reportService";
import { useDashboardStore } from "@/store/dashboardStore";

interface Props {
  onGenerated: () => void;
}

export default function GenerateReportButton({ onGenerated }: Props) {
  const activeShiftId = useDashboardStore((s) => s.activeShiftId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleClick = async () => {
    if (!activeShiftId) return;
    setLoading(true);
    setError(null);
    try {
      await generateReport({ shift_id: activeShiftId, patrol_summaries: [], alert_summaries: [] });
      onGenerated();
    } catch {
      setError("Report generation failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleClick}
        disabled={loading || !activeShiftId}
        className="bg-indigo-600 text-white rounded px-4 py-2 text-sm disabled:opacity-50"
        title={!activeShiftId ? "No active shift selected" : undefined}
      >
        {loading ? "Generating…" : "Generate Audit Report"}
      </button>
      {error && <p className="text-red-500 text-xs">{error}</p>}
    </div>
  );
}
