"use client";
import { useEffect, useState } from "react";
import { subscribeToFloorPlans } from "@/services/floorPlanService";
import { useAuth } from "./useAuth";
import type { FloorPlanRecord } from "@/types/floorPlan";

export function useFloorPlans(): {
  floorPlans: FloorPlanRecord[];
  activeFloorPlan: FloorPlanRecord | null;
  isLoading: boolean;
} {
  const { user } = useAuth();
  const [floorPlans, setFloorPlans] = useState<FloorPlanRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user?.uid) return;

    setIsLoading(true);

    const unsubscribe = subscribeToFloorPlans(user.uid, (plans) => {
      setFloorPlans(plans);
      setIsLoading(false);
    });

    return () => unsubscribe();
  }, [user?.uid]); // uid string — stable, won't re-run on object identity change

  const activeFloorPlan = floorPlans.find((p) => p.is_active) ?? null;
  return { floorPlans, activeFloorPlan, isLoading };
}
