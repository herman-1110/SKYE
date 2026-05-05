"use client";

interface Zone { name: string; x: number; y: number; w: number; h: number; highRisk: boolean }

const ZONES_M: Zone[] = [
  { name: "Loading Bay",       x:  0, y:  0, w: 20, h: 10, highRisk: true  },
  { name: "Forklift Corridor", x:  0, y: 10, w: 40, h:  5, highRisk: true  },
  { name: "Assembly Floor",    x: 20, y:  0, w: 40, h: 30, highRisk: false },
  { name: "Storage Rack A",    x: 60, y:  0, w: 20, h: 15, highRisk: true  },
  { name: "Storage Rack B",    x: 60, y: 15, w: 20, h: 15, highRisk: true  },
  { name: "Control Room",      x:  0, y: 30, w: 15, h: 10, highRisk: false },
  { name: "Exit Corridor",     x: 15, y: 30, w: 65, h: 10, highRisk: false },
];

const MAP_W_M = 80;
const MAP_H_M = 40;

export default function ZoneOverlay({ canvasW, canvasH }: { canvasW: number; canvasH: number }) {
  const sx = canvasW / MAP_W_M;
  const sy = canvasH / MAP_H_M;

  return (
    <svg
      viewBox={`0 0 ${canvasW} ${canvasH}`}
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden
    >
      {ZONES_M.map((z) => (
        <g key={z.name}>
          <rect
            x={z.x * sx} y={z.y * sy} width={z.w * sx} height={z.h * sy}
            fill={z.highRisk ? "rgba(239,68,68,0.10)" : "rgba(16,185,129,0.06)"}
            stroke={z.highRisk ? "rgba(239,68,68,0.5)" : "rgba(16,185,129,0.3)"}
            strokeWidth={1}
          />
          <text
            x={z.x * sx + 4} y={z.y * sy + 11}
            fontSize={8} fill={z.highRisk ? "rgba(239,68,68,0.8)" : "rgba(16,185,129,0.7)"}
            fontFamily="monospace"
          >
            {z.name.toUpperCase()}
          </text>
        </g>
      ))}
    </svg>
  );
}
