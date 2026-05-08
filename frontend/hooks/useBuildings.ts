"use client";
import { useEffect, useState } from "react";
import { useAuth } from "./useAuth";
import { subscribeToBuildings } from "@/services/buildingService";
import { useDashboardStore } from "@/store/dashboardStore";
import type { BuildingRecord } from "@/types/building";

export function useBuildings(): { buildings: BuildingRecord[]; isLoading: boolean } {
  const { user } = useAuth();
  const { cachedBuildings, setCachedBuildings } = useDashboardStore();
  const [buildings, setBuildings] = useState<BuildingRecord[]>(cachedBuildings);
  const [isLoading, setIsLoading] = useState(cachedBuildings.length === 0);

  useEffect(() => {
    if (!user?.uid) return;
    const unsub = subscribeToBuildings(user.uid, (data) => {
      setBuildings(data);
      setCachedBuildings(data);
      setIsLoading(false);
    });
    return () => unsub();
  }, [user?.uid]); // eslint-disable-line react-hooks/exhaustive-deps

  return { buildings, isLoading };
}
