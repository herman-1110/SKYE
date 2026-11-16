import { create } from "zustand";

// Per-tab state for the critical-alert banner (Prompt 145). Which alerts show
// is worked out from the live /alerts data (useCriticalQueue in useAlerts);
// this store only holds what this tab did to them, so a reload clears it.
interface CriticalAlertState {
  // Hidden in this tab only: a non-admin's ✕, or an admin's acknowledge that
  // went through (the live data then says the same in every tab).
  hiddenIds: Set<string>;
  // Acknowledges in flight, so ✕ isn't sent twice.
  pendingIds: Set<string>;
  hide: (alert_id: string) => void;
  setPending: (alert_id: string, pending: boolean) => void;
}

export const useCriticalAlertStore = create<CriticalAlertState>((set) => ({
  hiddenIds: new Set(),
  pendingIds: new Set(),
  hide: (alert_id) =>
    set((s) => (s.hiddenIds.has(alert_id) ? s : { hiddenIds: new Set([...s.hiddenIds, alert_id]) })),
  setPending: (alert_id, pending) =>
    set((s) => {
      if (s.pendingIds.has(alert_id) === pending) return s;
      const next = new Set(s.pendingIds);
      if (pending) next.add(alert_id);
      else next.delete(alert_id);
      return { pendingIds: next };
    }),
}));
