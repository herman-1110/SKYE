"use client";
import { useState, useEffect } from "react";
import { getZones } from "@/services/zoneService";
import type { ZoneRecord } from "@/types/zone";

export function useZones(
  buildingId: string | null | undefined,
  floorId: string | null | undefined,
) {
  const [zones, setZones] = useState<ZoneRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!buildingId || !floorId) { setZones([]); return; }
    setIsLoading(true);
    getZones(buildingId, floorId)
      .then((data) => { setZones(data); setIsLoading(false); })
      .catch(() => setIsLoading(false));
  }, [buildingId, floorId]);

  return { zones, setZones, isLoading };
}
