"use client";
import { useEffect, useState } from "react";
import {
  subscribeToAlerts,
  unsubscribeFromAlerts,
} from "@/services/alertService";
import { useDashboardStore } from "@/store/dashboardStore";
import { useCriticalAlertStore } from "@/store/criticalAlertStore";
import type { AlertRecord } from "@/types/alert";

const CRITICAL_TYPES = new Set(["man_down", "collision"]);

export function useAlerts(): {
  alerts: Record<string, AlertRecord>;
  isLoading: boolean;
} {
  const setAlerts = useDashboardStore((s) => s.setAlerts);
  const alerts = useDashboardStore((s) => s.alerts);
  const [isLoading, setIsLoading] = useState(true);
  const addCritical = useCriticalAlertStore((s) => s.addCritical);
  const seenIds = useCriticalAlertStore((s) => s.seenIds);

  useEffect(() => {
    subscribeToAlerts((data) => {
      setAlerts(data);
      setIsLoading(false);
      // Detect new unresolved critical alerts
      Object.values(data).forEach((alert) => {
        if (
          CRITICAL_TYPES.has(alert.alert_type) &&
          !alert.resolved &&
          !seenIds.has(alert.alert_id)
        ) {
          addCritical(alert);
        }
      });
    });
    return () => unsubscribeFromAlerts();
  }, [setAlerts, addCritical, seenIds]);

  return { alerts, isLoading };
}
