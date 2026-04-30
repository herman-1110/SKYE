import {
  collection,
  onSnapshot,
  orderBy,
  query,
  type Unsubscribe,
} from "firebase/firestore";
import { fsdb } from "@/config/firebase";
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
