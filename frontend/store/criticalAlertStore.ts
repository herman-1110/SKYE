import { create } from "zustand";
import type { AlertRecord } from "@/types/alert";

interface CriticalAlertState {
  queue: AlertRecord[];
  seenIds: Set<string>;
  addCritical: (alert: AlertRecord) => void;
  dismissCritical: (alert_id: string) => void;
}

export const useCriticalAlertStore = create<CriticalAlertState>((set) => ({
  queue: [],
  seenIds: new Set(),
  addCritical: (alert) =>
    set((s) => {
      if (s.seenIds.has(alert.alert_id)) return s;
      return {
        queue: [...s.queue, alert],
        seenIds: new Set([...s.seenIds, alert.alert_id]),
      };
    }),
  dismissCritical: (alert_id) =>
    set((s) => ({
      queue: s.queue.filter((a) => a.alert_id !== alert_id),
    })),
}));
