import {
  collection,
  onSnapshot,
  orderBy,
  query,
  type Unsubscribe,
} from "firebase/firestore";
import { fsdb } from "@/config/firebase";
import { authFetch } from "@/utils/apiClient";
import type { AuditReportRecord } from "@/types/auditReport";

type Callback = (reports: AuditReportRecord[]) => void;

let _unsubscribe: Unsubscribe | null = null;

export function subscribeToReports(callback: Callback): void {
  const q = query(
    collection(fsdb, "audit_reports"),
    orderBy("generated_at", "desc"),
  );
  _unsubscribe = onSnapshot(q, (snapshot) => {
    callback(snapshot.docs.map((doc) => doc.data() as AuditReportRecord));
  });
}

export function unsubscribeFromReports(): void {
  _unsubscribe?.();
  _unsubscribe = null;
}

export interface ReportableShift {
  log_id: string;
  guard_id: string;
  guard_label: string;
  shift_start: number | null;
  shift_end: number | null;
}

export async function fetchReportableShifts(): Promise<ReportableShift[]> {
  const res = await authFetch("/api/reports/shifts");
  if (!res.ok) throw new Error(`Failed to fetch shifts: ${res.status}`);
  const data = await res.json();
  return data.shifts ?? [];
}

export async function generateReport(params: { log_id: string }): Promise<AuditReportRecord> {
  const res = await authFetch("/api/reports/generate", {
    method: "POST",
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Report generation failed: ${res.status}`);
  return res.json() as Promise<AuditReportRecord>;
}
