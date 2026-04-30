"use client";
import { useEffect, useState } from "react";
import {
  subscribeToAlerts,
  unsubscribeFromAlerts,
} from "@/services/alertService";
import { useDashboardStore } from "@/store/dashboardStore";
import type { AlertRecord } from "@/types/alert";

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
