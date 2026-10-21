"use client";
import { useEffect, useState } from "react";
import { subscribeToFloors } from "@/services/floorService";
import type { FloorRecord } from "@/types/floor";

export function useFloors(buildingId: string | null | undefined): {
  floors: FloorRecord[];
  activeFloor: FloorRecord | null;
  activeFloors: FloorRecord[];
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

  // Several floors can be active at once (Prompt 142). activeFloor stays the
  // first of them, in floor-number order: the default wherever one is shown.
  const activeFloors = floors.filter((f) => f.is_active);
  const activeFloor = activeFloors[0] ?? null;
  return { floors, activeFloor, activeFloors, isLoading };
}

/** The first of these buildings, in order, that has an active floor. Each
 *  building's floors are read through the same subscription useFloors uses:
 *  the rules allow no collection-group query from the dashboard (Prompt 142,
 *  D1.10). undefined until every building has answered; null if none has one. */
export function useFirstBuildingWithActiveFloor(buildingIds: string[]): string | null | undefined {
  const [hasActive, setHasActive] = useState<Record<string, boolean>>({});
  const key = buildingIds.join(",");

  useEffect(() => {
    setHasActive({});
    const unsubs = buildingIds.map((id) =>
      subscribeToFloors(id, (data) => setHasActive((prev) => ({ ...prev, [id]: data.some((f) => f.is_active) }))),
    );
    return () => unsubs.forEach((unsub) => unsub());
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  if (buildingIds.some((id) => !(id in hasActive))) return undefined;
  return buildingIds.find((id) => hasActive[id]) ?? null;
}
