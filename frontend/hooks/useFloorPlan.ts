"use client";
import { useEffect, useState } from "react";
import { subscribeToActiveFloorPlan } from "@/services/floorPlanService";
import type { FloorPlanRecord } from "@/types/floorPlan";

export function useActiveFloorPlan(): { floorPlan: FloorPlanRecord | null; isLoading: boolean } {
  const [floorPlan, setFloorPlan] = useState<FloorPlanRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = subscribeToActiveFloorPlan((plan) => {
      setFloorPlan(plan);
      setIsLoading(false);
    });
    return unsubscribe;
  }, []);

  return { floorPlan, isLoading };
}
