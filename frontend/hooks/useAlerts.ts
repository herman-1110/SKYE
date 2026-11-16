"use client";
import { useEffect, useMemo, useState } from "react";
import {
  subscribeToAlerts,
  unsubscribeFromAlerts,
} from "@/services/alertService";
import { useDashboardStore } from "@/store/dashboardStore";
import { useCriticalAlertStore } from "@/store/criticalAlertStore";
import type { AlertRecord } from "@/types/alert";

export const CRITICAL_TYPES = new Set(["man_down", "collision", "possible_man_down", "positioning_offline"]);

export function useAlerts(): {
  alerts: Record<string, AlertRecord>;
  isLoading: boolean;
} {
  const setAlerts = useDashboardStore((s) => s.setAlerts);
  const alerts = useDashboardStore((s) => s.alerts);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    subscribeToAlerts((data) => {
      setAlerts(data);
      setIsLoading(false);
    });
    return () => unsubscribeFromAlerts();
  }, [setAlerts]);

  return { alerts, isLoading };
}

// The banner's queue (Prompt 145, D2.1 and D2.4), worked out from the live
// alerts whenever they change: critical, unresolved, not acknowledged, and not
// hidden in this tab. So an alert raised while nobody had the dashboard open
// still pops up at the next login, and one that's resolved, acknowledged or
// deleted leaves by itself. Oldest first, the order they used to arrive in.
export function useCriticalQueue(): AlertRecord[] {
  const alerts = useDashboardStore((s) => s.alerts);
  const hiddenIds = useCriticalAlertStore((s) => s.hiddenIds);
  return useMemo(
    () =>
      Object.values(alerts ?? {})
        .filter(
          (a): a is AlertRecord =>
            !!a &&
            typeof a === "object" &&
            typeof a.alert_id === "string" &&
            CRITICAL_TYPES.has(a.alert_type) &&
            !a.resolved &&
            !a.acknowledged_at &&
            !hiddenIds.has(a.alert_id),
        )
        .sort((a, b) => (a.timestamp ?? "").localeCompare(b.timestamp ?? "")),
    [alerts, hiddenIds],
  );
}
