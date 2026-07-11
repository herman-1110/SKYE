"use client";
import type { PositionRecord } from "@/types/position";

interface Props {
  position: PositionRecord;
  px: number;
  py: number;
  scale: number | null;   // pixels per metre, for converting radius_m into SVG units
  onHover: (payload: { position: PositionRecord; x: number; y: number } | null) => void;
}

const TYPE_COLOUR: Record<string, string> = {
  guard: "var(--success)",
  worker: "var(--info)",
  forklift: "var(--warning)",
};

export default function WorkerMarker({ position, px, py, scale, onHover }: Props) {
  const fill = TYPE_COLOUR[position.person_type] ?? "var(--text-secondary)";
  const radiusPx =
    position.is_approximate && position.radius_m != null && scale
      ? position.radius_m * scale
      : null;

  return (
    <g style={{ pointerEvents: "all" }}>
      {/* Approximate-position uncertainty circle — dashed, non-interactive so it
          never steals hover/click from AP/CCTV markers or zones underneath it. */}
      {radiusPx != null && (
        <circle
          cx={px} cy={py} r={radiusPx}
          fill={fill} fillOpacity={0.08}
          stroke={fill} strokeOpacity={0.55} strokeWidth={1.5}
          strokeDasharray="5 4"
          style={{ pointerEvents: "none" }}
        />
      )}
      <circle cx={px} cy={py} r={12} fill={fill} fillOpacity={0.15} />
      <circle
        cx={px} cy={py} r={7}
        fill={fill}
        stroke="var(--bg-base)"
        strokeWidth={2}
        style={{ cursor: "pointer" }}
        onMouseEnter={(e) => onHover({ position, x: e.clientX, y: e.clientY })}
        onMouseMove={(e) => onHover({ position, x: e.clientX, y: e.clientY })}
        onMouseLeave={() => onHover(null)}
      />
    </g>
  );
}
