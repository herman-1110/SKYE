"use client";
import { useState } from "react";
import type { PositionRecord } from "@/types/position";

interface Props { position: PositionRecord; px: number; py: number }

const COLOUR: Record<string, string> = {
  guard:    "#10b981",
  worker:   "#60a5fa",
  forklift: "#f59e0b",
};

export default function WorkerMarker({ position, px, py }: Props) {
  const [hovered, setHovered] = useState(false);
  const fill = COLOUR[position.person_type] ?? "#94a3b8";

  return (
    <g>
      {/* Outer ring for alert state */}
      <circle cx={px} cy={py} r={12} fill={`${fill}20`} />
      <circle
        cx={px} cy={py} r={7}
        fill={fill}
        stroke="#0a0c0f"
        strokeWidth={2}
        className="cursor-pointer transition-all duration-150"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {hovered && (
        <foreignObject x={px + 14} y={py - 36} width={180} height={80}>
          <div className="bg-s-elevated border border-s-border rounded-lg shadow-xl p-2.5 space-y-1 text-xs">
            <p className="font-semibold text-s-text truncate">{position.person_id}</p>
            <p className="font-mono text-s-muted">{position.zone}</p>
            <p className="font-mono text-s-mono text-[10px]">
              {position.x.toFixed(1)}m, {position.y.toFixed(1)}m
            </p>
          </div>
        </foreignObject>
      )}
    </g>
  );
}
