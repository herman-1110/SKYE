"use client";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useBuildings } from "@/hooks/useBuildings";
import { useFloors } from "@/hooks/useFloors";
import { useDashboardStore } from "@/store/dashboardStore";
import { activateFloor } from "@/services/floorService";
import { toast } from "@/store/toastStore";
import FloorMap from "@/components/map/FloorMap";
import DeviceStatusPanel from "@/components/dashboard/DeviceStatusPanel";
import SelectDropdown from "@/components/shared/SelectDropdown";
import type { PositionRecord } from "@/types/position";
import type { BuildingRecord } from "@/types/building";
import type { FloorRecord } from "@/types/floor";

export default function FloorMapArea() {
  const { userRecord } = useAuth();
  const isAdmin = userRecord?.role === "admin";
  const { buildings, isLoading: buildingsLoading } = useBuildings();
  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null);
  const { floors, activeFloor, isLoading: floorsLoading } = useFloors(selectedBuildingId);
  const [selectedFloorId, setSelectedFloorId] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const positions = useDashboardStore((s) => s.positions);

  const positionList = useMemo(() => {
    const all = Object.values(positions) as PositionRecord[];
    const floorId = (floors.find((f) => f.id === selectedFloorId) ?? activeFloor)?.id;
    if (!floorId) return [];
    return all.filter((p) => p.floor_id === floorId);
  }, [positions, selectedFloorId, floors, activeFloor]);

  // Auto-select the first building + its active floor
  useEffect(() => {
    if (buildings.length > 0 && !selectedBuildingId) {
      setSelectedBuildingId(buildings[0].id);
    }
  }, [buildings, selectedBuildingId]);

  useEffect(() => {
    if (activeFloor) {
      setSelectedFloorId(activeFloor.id);
    } else {
      setSelectedFloorId(null);
    }
  }, [activeFloor]);

  const displayedFloor = floors.find((f) => f.id === selectedFloorId && f.is_active) ?? activeFloor;

  const handleBuildingChange = (id: string) => {
    setSelectedBuildingId(id);
    setSelectedFloorId(null);
  };

  const handleFloorChange = async (floorId: string) => {
    if (!selectedBuildingId || switching || floorId === selectedFloorId) return;
    setSelectedFloorId(floorId);
    setSwitching(true);
    try {
      await activateFloor(selectedBuildingId, floorId);
    } catch {
      toast.error("Failed to switch floor.");
    } finally {
      setSwitching(false);
    }
  };

  const isLoading = buildingsLoading || floorsLoading;

  if (isLoading) {
    return <div className="h-64 rounded-xl bg-s-surface border border-s-border skeleton" />;
  }

  if (buildings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 rounded-xl bg-s-surface border border-dashed border-s-border text-center gap-4">
        <svg className="text-s-muted" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/>
          <line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>
        </svg>
        <div>
          <p className="text-s-text font-medium">No Floor Plans</p>
          <p className="text-s-muted text-sm mt-1">
            {isAdmin
              ? "Create a building and upload a floor plan to enable live tracking"
              : "No floor plans available. Contact your administrator."}
          </p>
        </div>
      </div>
    );
  }

  if (!isLoading && floors.length > 0 && !activeFloor) {
    return (
      <div className="flex flex-col items-center justify-center h-64 rounded-xl bg-s-surface border border-dashed border-s-border text-center gap-4">
        <svg className="text-s-muted" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/>
          <line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>
        </svg>
        <div>
          <p className="text-s-text font-medium">No Active Floor Plan</p>
          <p className="text-s-muted text-sm mt-1">
            {isAdmin
              ? "Set a floor as active in the Floor Plans tab to display it here"
              : "No floor plan is currently active. Contact your administrator."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Building + floor selectors */}
      <div className="flex items-center gap-2">
        {buildings.length > 1 && (
          <SelectDropdown<BuildingRecord>
            label="Building"
            items={buildings}
            selectedId={selectedBuildingId}
            getId={(b) => b.id}
            getLabel={(b) => b.name}
            onSelect={handleBuildingChange}
            placeholder="Select Building"
          />
        )}

        {floors.length > 1 && (
          <>
            <SelectDropdown<FloorRecord>
              label="Floor"
              items={floors}
              selectedId={selectedFloorId}
              getId={(f) => f.id}
              getLabel={(f) => `${f.name}${f.is_active ? " — ACTIVE" : ""}`}
              onSelect={handleFloorChange}
              disabled={switching}
              placeholder="Select Floor"
            />
            {switching && <span className="h-3 w-3 rounded-full border-2 border-s-accent border-t-transparent animate-spin shrink-0" />}
          </>
        )}
      </div>

      <div className="w-full">
        <FloorMap
          positions={positionList}
          buildingId={selectedBuildingId}
          activeFloor={displayedFloor ?? null}
        />
      </div>

      <DeviceStatusPanel
        buildingId={selectedBuildingId}
        floorId={displayedFloor?.id ?? null}
      />
    </div>
  );
}
