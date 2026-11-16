import { type DataSnapshot, off, onValue, ref } from "firebase/database";
import { db } from "@/config/firebase";
import type { AlertRecord, FeedbackValue } from "@/types/alert";
import { authFetch } from "@/utils/apiClient";

type Callback = (alerts: Record<string, AlertRecord>) => void;

let _off: (() => void) | null = null;

export function subscribeToAlerts(callback: Callback): void {
  const r = ref(db, "/alerts");
  const handler = (snap: DataSnapshot) =>
    callback((snap.val() as Record<string, AlertRecord>) ?? {});
  onValue(r, handler);
  _off = () => off(r, "value", handler);
}

export function unsubscribeFromAlerts(): void {
  _off?.();
  _off = null;
}

export async function deleteAlert(alertId: string): Promise<void> {
  const res = await authFetch(`/api/alerts/${alertId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Alert deletion failed: ${res.status}`);
}

export async function submitFeedback(
  alertId: string,
  feedback: FeedbackValue,
  reason: string,
): Promise<void> {
  const res = await authFetch(`/api/alerts/${alertId}/feedback`, {
    method: "POST",
    body: JSON.stringify({
      feedback,
      reason: reason.trim() === "" ? null : reason.trim(),
    }),
  });
  if (!res.ok) throw new Error(`Feedback submission failed: ${res.status}`);
}

export interface Acknowledgement {
  alert_id: string;
  acknowledged_at: string;
  acknowledged_by: string;
  acknowledged_by_uid: string;
}

// Closes an alert's pop-up for everyone (admins and the owner; Prompt 145).
// The backend keeps the first acknowledgement if there's already one. On
// failure, throws an Error whose message is a sentence fit for a toast.
export async function acknowledgeAlert(alertId: string): Promise<Acknowledgement> {
  const res = await authFetch(`/api/alerts/${encodeURIComponent(alertId)}/acknowledge`, {
    method: "POST",
  });
  if (!res.ok) {
    let reason = "";
    try {
      const body = (await res.json()) as { detail?: unknown; error?: unknown };
      if (typeof body.detail === "string") reason = body.detail;
      else if (typeof body.error === "string") reason = body.error;
    } catch {
      // not JSON: the status below says enough
    }
    if (!reason) reason = `The server answered ${res.status}`;
    throw new Error(reason.endsWith(".") ? reason : `${reason}.`);
  }
  return (await res.json()) as Acknowledgement;
}
