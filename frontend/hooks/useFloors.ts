"use client";
import { useEffect, useState } from "react";
import { subscribeToFloors } from "@/services/floorService";
import type { FloorRecord } from "@/types/floor";

export function useFloors(buildingId: string | null | undefined): {
  floors: FloorRecord[];
  activeFloor: FloorRecord | null;
  isLoading: boolean;
} {
  const [floors, setFloors] = useState<FloorRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!buildingId) { setFloors([]); return; }
    setIsLoading(true);
    const unsub = subscribeToFloors(buildingId, (data) => {
      setFloors(data);
      setIsLoading(false);
    });
    return () => unsub();
  }, [buildingId]);

  const activeFloor = floors.find((f) => f.is_active) ?? null;
  return { floors, activeFloor, isLoading };
}
