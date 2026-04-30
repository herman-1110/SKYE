import { type DataSnapshot, off, onValue, ref } from "firebase/database";
import { db } from "@/config/firebase";
import type { AlertRecord, FeedbackValue } from "@/types/alert";

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

export async function submitFeedback(
  alertId: string,
  feedback: FeedbackValue,
  reason: string,
): Promise<void> {
  const res = await fetch(`/api/alerts/${alertId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback, reason }),
  });
  if (!res.ok) throw new Error(`Feedback submission failed: ${res.status}`);
}
