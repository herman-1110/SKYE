"use client";
import type { PositionRecord } from "@/types/position";

interface Props {
  position: PositionRecord;
  px: number;
  py: number;
  scale: number | null;   // pixels per metre, for converting radius_m into SVG units
}

const TYPE_COLOUR: Record<string, string> = {
  guard: "var(--success)",
  worker: "var(--info)",
  forklift: "var(--warning)",
};

// Purely visual — no hover handlers here. When two beacons anchor to the same
// AP (or their approximate circles otherwise overlap), the DOM can only ever
// deliver a hover event to the one topmost element at that pixel, so per-marker
// hover would silently hide every beacon underneath it. FloorMap computes hits
// itself instead (checking every beacon's px/py/radius against the cursor), so
// an overlap can report ALL of them. See FloorMap's hoveredWorkers.
export default function WorkerMarker({ position, px, py, scale }: Props) {
  const fill = TYPE_COLOUR[position.person_type] ?? "var(--text-secondary)";
  const radiusPx =
    position.is_approximate && position.radius_m != null && scale
      ? position.radius_m * scale
      : null;

  return (
    <g style={{ pointerEvents: "none" }}>
      {/* Approximate-position uncertainty circle — one per beacon anchored to
          a single AP, radius = RSSI-estimated distance to that AP. */}
      {radiusPx != null && (
        <circle
          cx={px} cy={py} r={radiusPx}
          fill={fill} fillOpacity={0.08}
          stroke={fill} strokeOpacity={0.55} strokeWidth={1.5}
          strokeDasharray="5 4"
        />
      )}
      <circle cx={px} cy={py} r={12} fill={fill} fillOpacity={0.15} />
      <circle cx={px} cy={py} r={7} fill={fill} stroke="var(--bg-base)" strokeWidth={2} />
    </g>
  );
}
