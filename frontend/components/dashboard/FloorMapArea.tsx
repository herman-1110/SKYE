"use client";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useBuildings } from "@/hooks/useBuildings";
import { useFirstBuildingWithActiveFloor, useFloors } from "@/hooks/useFloors";
import { useDashboardStore } from "@/store/dashboardStore";
import FloorMap from "@/components/map/FloorMap";
import DeviceStatusPanel from "@/components/dashboard/DeviceStatusPanel";
import SelectDropdown from "@/components/shared/SelectDropdown";
import { isAdminRole } from "@/types/user";
import type { PositionRecord } from "@/types/position";
import type { BuildingRecord } from "@/types/building";
import type { FloorRecord } from "@/types/floor";

export default function FloorMapArea() {
  const { userRecord } = useAuth();
  const isAdmin = isAdminRole(userRecord?.role);
  const { buildings, isLoading: buildingsLoading } = useBuildings();
  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null);
  const { floors, activeFloors, isLoading: floorsLoading } = useFloors(selectedBuildingId);
  const [selectedFloorId, setSelectedFloorId] = useState<string | null>(null);
  const firstActiveBuildingId = useFirstBuildingWithActiveFloor(buildings.map((b) => b.id));
  const positions = useDashboardStore((s) => s.positions);

  // Several floors can be active at once (Prompt 142, D1.10): the dashboard
  // shows one of the selected building's active floors, the chosen one while
  // it stays active, else the first. Choosing only changes the view.
  const displayedFloor = activeFloors.find((f) => f.id === selectedFloorId) ?? activeFloors[0] ?? null;

  const positionList = useMemo(() => {
    const all = Object.values(positions) as PositionRecord[];
    const floorId = displayedFloor?.id;
    if (!floorId) return [];
    return all.filter((p) => p.floor_id === floorId);
  }, [positions, displayedFloor?.id]);

  // Auto-select the first building that has an active floor, or the first
  // building if none has.
  useEffect(() => {
    if (buildings.length > 0 && !selectedBuildingId && firstActiveBuildingId !== undefined) {
      setSelectedBuildingId(firstActiveBuildingId ?? buildings[0].id);
    }
  }, [buildings, selectedBuildingId, firstActiveBuildingId]);

  const handleBuildingChange = (id: string) => {
    setSelectedBuildingId(id);
    setSelectedFloorId(null);
  };

  const isLoading = buildingsLoading || floorsLoading || (buildings.length > 0 && !selectedBuildingId);

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

  if (!isLoading && floors.length > 0 && activeFloors.length === 0) {
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

        {activeFloors.length > 1 && (
          <SelectDropdown<FloorRecord>
            label="Floor"
            items={activeFloors}
            selectedId={displayedFloor?.id ?? null}
            getId={(f) => f.id}
            getLabel={(f) => f.name}
            onSelect={setSelectedFloorId}
            placeholder="Select Floor"
          />
        )}
      </div>

      <div className="w-full">
        <FloorMap
          positions={positionList}
          buildingId={selectedBuildingId}
          activeFloor={displayedFloor}
        />
      </div>

      <DeviceStatusPanel
        buildingId={selectedBuildingId}
        floorId={displayedFloor?.id ?? null}
      />
    </div>
  );
}
