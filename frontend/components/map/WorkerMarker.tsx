"use client";
import { useState } from "react";
import type { PositionRecord } from "@/types/position";

interface Props {
  position: PositionRecord;
  px: number;
  py: number;
}

const COLOUR: Record<PositionRecord["person_type"], string> = {
  guard:    "#2563eb",
  worker:   "#16a34a",
  forklift: "#d97706",
};

export default function WorkerMarker({ position, px, py }: Props) {
  const [hovered, setHovered] = useState(false);
  const fill = COLOUR[position.person_type] ?? "#6b7280";

  return (
    <g>
      <circle
        cx={px} cy={py} r={8}
        fill={fill} stroke="white" strokeWidth={2}
        className="cursor-pointer"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      {hovered && (
        <foreignObject x={px + 12} y={py - 24} width={160} height={68}>
          <div className="bg-white text-xs rounded shadow-md border p-1.5 space-y-0.5">
            <p className="font-semibold truncate">{position.person_id}</p>
            <p className="text-gray-500">{position.zone}</p>
            <p className="text-gray-400">
              ({position.x.toFixed(1)}, {position.y.toFixed(1)}) m
            </p>
          </div>
        </foreignObject>
      )}
    </g>
  );
}
