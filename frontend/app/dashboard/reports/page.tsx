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
  // Firestore onSnapshot delivers an already-ordered AuditReportRecord[]
  const [reports, setReports] = useState<AuditReportRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    subscribeToReports((data) => {
      setReports(data);
      setIsLoading(false);
    });
    return () => unsubscribeFromReports();
  }, []);

  if (isLoading) return <LoadingSpinner />;

  return (
    <main className="p-4 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Audit Reports</h1>
        <GenerateReportButton onGenerated={() => {}} />
      </div>
      {reports.length === 0 ? (
        <p className="text-sm text-gray-500">No reports generated yet.</p>
      ) : (
        reports.map((r) => <ReportCard key={r.report_id} report={r} />)
      )}
    </main>
  );
}
