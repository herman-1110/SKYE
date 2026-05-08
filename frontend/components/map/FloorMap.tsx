"use client";
import { useState } from "react";
import type { PositionRecord } from "@/types/position";
import type { FloorRecord } from "@/types/floor";
import { useZones } from "@/hooks/useZones";
import WorkerMarker from "./WorkerMarker";

interface Props {
  positions: PositionRecord[];
  buildingId: string | null;
  activeFloor: FloorRecord | null;
}

const MAP_W_M = 80;
const MAP_H_M = 40;
const CANVAS_W = 800;
const CANVAS_H = 400;

export default function FloorMap({ positions, buildingId, activeFloor }: Props) {
  const [showZones, setShowZones] = useState(true);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const { zones } = useZones(buildingId, activeFloor?.id ?? null);

  const scale = activeFloor?.scale_pixels_per_meter ?? null;

  const toPixel = (p: PositionRecord): { px: number; py: number } => {
    if (p.pixel_x != null && p.pixel_y != null) {
      return { px: p.pixel_x, py: p.pixel_y };
    }
    return {
      px: (p.x / MAP_W_M) * CANVAS_W,
      py: (p.y / MAP_H_M) * CANVAS_H,
    };
  };

  const toPct = (metres: number, axis: "x" | "y"): number => {
    if (!naturalSize || !scale) return 0;
    return ((metres * scale) / (axis === "x" ? naturalSize.w : naturalSize.h)) * 100;
  };

  if (!activeFloor) {
    return (
      <div className="flex items-center justify-center h-64 rounded-xl bg-s-surface border border-s-border text-s-muted">
        <p className="text-sm">No active floor plan</p>
      </div>
    );
  }

  return (
    <div className="relative w-full rounded-xl overflow-hidden border border-s-border bg-s-elevated shadow-sm">
      <img
        src={activeFloor.url}
        alt={activeFloor.name}
        className="w-full h-auto"
        style={{ aspectRatio: "2 / 1" }}
        onLoad={(e) => {
          const img = e.currentTarget;
          setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
        }}
      />

      {/* Zone overlays — pointer-events: none so markers remain clickable */}
      {showZones && naturalSize && scale &&
        zones.map((zone) => (
          <div
            key={zone.id}
            title={`${zone.name}${zone.is_high_risk ? " (High Risk)" : ""}`}
            style={{
              position: "absolute",
              left: `${toPct(zone.x_min, "x")}%`,
              top: `${toPct(zone.y_min, "y")}%`,
              width: `${toPct(zone.x_max - zone.x_min, "x")}%`,
              height: `${toPct(zone.y_max - zone.y_min, "y")}%`,
              backgroundColor: zone.color,
              pointerEvents: "none",
            }}
          >
            <span
              className="absolute top-1 left-1 font-mono text-[9px] tracking-widest px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: "rgba(0,0,0,0.45)",
                color: "#fff",
                pointerEvents: "none",
                whiteSpace: "nowrap",
              }}
            >
              {zone.name}
              {zone.is_high_risk && <span className="ml-1 text-red-400">⚠</span>}
            </span>
          </div>
        ))
      }

      {/* Worker markers */}
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

      {/* Zone toggle */}
      {zones.length > 0 && (
        <button
          onClick={() => setShowZones((v) => !v)}
          className="absolute top-2 right-2 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg font-mono text-[10px] tracking-widest transition-colors"
          style={{
            backgroundColor: showZones ? "rgba(245,158,11,0.15)" : "rgba(0,0,0,0.45)",
            color: showZones ? "#f59e0b" : "rgba(255,255,255,0.7)",
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {showZones ? (
              <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>
            ) : (
              <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></>
            )}
          </svg>
          ZONES
        </button>
      )}

      {/* Calibration warning */}
      {!activeFloor.scale_pixels_per_meter && (
        <div className="absolute bottom-0 inset-x-0 flex items-center gap-2 px-4 py-2.5 bg-s-elevated/95 border-t border-s-border backdrop-blur-sm">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-s-accent shrink-0">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <p className="font-mono text-[10px] text-s-muted tracking-wide">
            Floor plan not calibrated — worker positions may be inaccurate.
            Set scale in the <span className="text-s-text">Floor Plans</span> tab.
          </p>
        </div>
      )}
    </div>
  );
}
