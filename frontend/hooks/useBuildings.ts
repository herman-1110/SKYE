"use client";
import { useEffect, useState } from "react";
import { useAuth } from "./useAuth";
import { subscribeToBuildings } from "@/services/buildingService";
import type { BuildingRecord } from "@/types/building";

export function useBuildings(): { buildings: BuildingRecord[]; isLoading: boolean } {
  const { user } = useAuth();
  const [buildings, setBuildings] = useState<BuildingRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user?.uid) return;
    setIsLoading(true);
    const unsub = subscribeToBuildings(user.uid, (data) => {
      setBuildings(data);
      setIsLoading(false);
    });
    return () => unsub();
  }, [user?.uid]);

  return { buildings, isLoading };
}
