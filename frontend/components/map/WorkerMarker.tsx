"use client";
import type { PositionRecord } from "@/types/position";

interface Props {
  position: PositionRecord;
  px: number;
  py: number;
  onHover: (payload: { position: PositionRecord; x: number; y: number } | null) => void;
}

const TYPE_COLOUR: Record<string, string> = {
  guard: "var(--success)",
  worker: "var(--info)",
  forklift: "var(--warning)",
};

export default function WorkerMarker({ position, px, py, onHover }: Props) {
  const fill = TYPE_COLOUR[position.person_type] ?? "var(--text-secondary)";

  return (
    <g style={{ pointerEvents: "all" }}>
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
