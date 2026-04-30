"use client";
import { useEffect, useState } from "react";
import {
  subscribeToPositions,
  unsubscribeFromPositions,
} from "@/services/positionService";
import { useDashboardStore } from "@/store/dashboardStore";
import type { PositionRecord } from "@/types/position";

export function usePositions(): {
  positions: Record<string, PositionRecord>;
  isLoading: boolean;
} {
  const setPositions = useDashboardStore((s) => s.setPositions);
  const positions = useDashboardStore((s) => s.positions);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    subscribeToPositions((data) => {
      setPositions(data);
      setIsLoading(false);
    });
    return () => unsubscribeFromPositions();
  }, [setPositions]);

  return { positions, isLoading };
}
