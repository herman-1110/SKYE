import { type DataSnapshot, off, onValue, ref } from "firebase/database";
import { db } from "@/config/firebase";
import type { AuditReportRecord } from "@/types/auditReport";

type Callback = (reports: Record<string, AuditReportRecord>) => void;

let _off: (() => void) | null = null;

export function subscribeToReports(callback: Callback): void {
  const r = ref(db, "/audit_reports");
  const handler = (snap: DataSnapshot) =>
    callback((snap.val() as Record<string, AuditReportRecord>) ?? {});
  onValue(r, handler);
  _off = () => off(r, "value", handler);
}

export function unsubscribeFromReports(): void {
  _off?.();
  _off = null;
}

interface GenerateParams {
  shift_id: string;
  patrol_summaries: object[];
  alert_summaries: object[];
}

export async function generateReport(params: GenerateParams): Promise<AuditReportRecord> {
  const res = await fetch("/api/reports/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Report generation failed: ${res.status}`);
  return res.json() as Promise<AuditReportRecord>;
}
