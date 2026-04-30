"use client";
import { useEffect, useState } from "react";
import {
  subscribeToReports,
  unsubscribeFromReports,
} from "@/services/reportService";
import type { AuditReportRecord } from "@/types/auditReport";
import ReportCard from "@/components/reports/ReportCard";
import GenerateReportButton from "@/components/reports/GenerateReportButton";
import LoadingSpinner from "@/components/shared/LoadingSpinner";

export default function ReportsPage() {
  const [reports, setReports] = useState<Record<string, AuditReportRecord>>({});
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    subscribeToReports((data) => {
      setReports(data);
      setIsLoading(false);
    });
    return () => unsubscribeFromReports();
  }, []);

  if (isLoading) return <LoadingSpinner />;

  const reportList = Object.values(reports).sort(
    (a, b) => b.generated_at.localeCompare(a.generated_at),
  );

  return (
    <main className="p-4 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Audit Reports</h1>
        <GenerateReportButton onGenerated={() => {}} />
      </div>
      {reportList.length === 0 ? (
        <p className="text-sm text-gray-500">No reports generated yet.</p>
      ) : (
        reportList.map((r) => <ReportCard key={r.report_id} report={r} />)
      )}
    </main>
  );
}
