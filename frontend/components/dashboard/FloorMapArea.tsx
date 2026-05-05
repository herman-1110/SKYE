"use client";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useActiveFloorPlan } from "@/hooks/useFloorPlan";
import { useDashboardStore } from "@/store/dashboardStore";
import FloorMap from "@/components/map/FloorMap";
import FloorPlanModal from "@/components/floor-plans/FloorPlanModal";
import type { PositionRecord } from "@/types/position";

export default function FloorMapArea() {
  const { user } = useAuth();
  const { floorPlan, isLoading } = useActiveFloorPlan();
  const positions = useDashboardStore((s) => s.positions);
  const [showModal, setShowModal] = useState(false);

  const positionList = Object.values(positions) as PositionRecord[];

  if (isLoading) {
    return <div className="h-64 rounded-xl bg-s-surface border border-s-border skeleton" />;
  }

  if (!floorPlan) {
    return (
      <>
        <div className="flex flex-col items-center justify-center h-64 rounded-xl bg-s-surface border border-dashed border-s-border text-center gap-4">
          <svg className="text-s-muted" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/>
            <line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>
          </svg>
          <div>
            <p className="text-s-text font-medium">No Floor Plan</p>
            <p className="text-s-muted text-sm mt-1">Upload your factory floor plan to enable live position tracking</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="px-5 py-2 rounded-lg bg-s-accent text-s-base font-semibold text-sm hover:opacity-90 transition-opacity"
          >
            Upload Floor Plan
          </button>
          <p className="text-xs text-s-muted">Supported: PNG, JPG — up to 10 MB</p>
        </div>
        {showModal && user && (
          <FloorPlanModal userId={user.uid} onClose={() => setShowModal(false)} />
        )}
      </>
    );
  }

  return (
    <div className="relative">
      <FloorMap positions={positionList} activeFloorPlan={floorPlan} />
      <button
        onClick={() => setShowModal(true)}
        className="absolute top-2 right-2 px-3 py-1.5 rounded-lg bg-s-elevated/80 border border-s-border text-xs text-s-muted hover:text-s-text backdrop-blur-sm transition-colors"
      >
        Change Floor Plan
      </button>
      {showModal && user && (
        <FloorPlanModal userId={user.uid} onClose={() => setShowModal(false)} />
      )}
    </div>
  );
}
