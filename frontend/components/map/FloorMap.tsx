"use client";
import type { PositionRecord } from "@/types/position";
import WorkerMarker from "./WorkerMarker";
import ZoneOverlay from "./ZoneOverlay";

interface Props {
  positions: PositionRecord[];
}

// Map dimensions must stay in sync with zone_utils.py ZONES
const MAP_W_M = 80;
const MAP_H_M = 40;
const CANVAS_W = 800;
const CANVAS_H = 400;

export default function FloorMap({ positions }: Props) {
  const toPixel = (x: number, y: number) => ({
    px: (x / MAP_W_M) * CANVAS_W,
    py: (y / MAP_H_M) * CANVAS_H,
  });

  return (
    <div className="relative w-full rounded-lg overflow-hidden border bg-white shadow">
      <img
        src="/floor-plan.png"
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
          const { px, py } = toPixel(p.x, p.y);
          return <WorkerMarker key={p.beacon_mac} position={p} px={px} py={py} />;
        })}
      </svg>
    </div>
  );
}
