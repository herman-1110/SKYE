import { type DataSnapshot, off, onValue, ref, remove } from "firebase/database";
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
  await remove(ref(db, `alerts/${alertId}`));
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
