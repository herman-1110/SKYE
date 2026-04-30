import { type DataSnapshot, off, onValue, ref } from "firebase/database";
import { db } from "@/config/firebase";
import type { PositionRecord } from "@/types/position";

type Callback = (positions: Record<string, PositionRecord>) => void;

let _off: (() => void) | null = null;

export function subscribeToPositions(callback: Callback): void {
  const r = ref(db, "/positions");
  const handler = (snap: DataSnapshot) =>
    callback((snap.val() as Record<string, PositionRecord>) ?? {});
  onValue(r, handler);
  _off = () => off(r, "value", handler);
}

export function unsubscribeFromPositions(): void {
  _off?.();
  _off = null;
}
