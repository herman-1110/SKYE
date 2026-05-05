"use client";
import type { PositionRecord } from "@/types/position";
import type { FloorPlanRecord } from "@/types/floorPlan";
import WorkerMarker from "./WorkerMarker";
import ZoneOverlay from "./ZoneOverlay";

interface Props {
  positions: PositionRecord[];
  activeFloorPlan: FloorPlanRecord | null;
}

// Fallback canvas dimensions used when no floor plan scale is calibrated.
// Must stay in sync with zone_utils.py ZONES when operating in metre mode.
const MAP_W_M = 80;
const MAP_H_M = 40;
const CANVAS_W = 800;
const CANVAS_H = 400;

export default function FloorMap({ positions, activeFloorPlan }: Props) {
  const floorPlanUrl = activeFloorPlan?.url ?? "/floor-plan.png";

  // If the backend has computed pixel_x/pixel_y (scale calibrated), use those directly.
  // Otherwise fall back to converting raw metres using the fixed canvas constants.
  const toPixel = (p: PositionRecord): { px: number; py: number } => {
    if (p.pixel_x != null && p.pixel_y != null) {
      return { px: p.pixel_x, py: p.pixel_y };
    }
    return {
      px: (p.x / MAP_W_M) * CANVAS_W,
      py: (p.y / MAP_H_M) * CANVAS_H,
    };
  };

  return (
    <div className="relative w-full rounded-lg overflow-hidden border bg-white shadow">
      <img
        src={floorPlanUrl}
        alt="Factory floor plan"
        className="w-full h-auto"
        style={{ aspectRatio: "2 / 1" }}
      />
      <ZoneOverlay canvasW={CANVAS_W} canvasH={CANVAS_H} />
      <svg
        viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
        className="absolute inset-0 w-full h-full"
        aria-label="Worker positions overlay"
      >
        {positions.map((p) => {
          const { px, py } = toPixel(p);
          return <WorkerMarker key={p.beacon_mac} position={p} px={px} py={py} />;
        })}
      </svg>
    </div>
  );
}
