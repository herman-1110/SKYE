"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import type { PositionRecord } from "@/types/position";
import type { FloorRecord } from "@/types/floor";
import { useZones } from "@/hooks/useZones";
import { useAPHeartbeats } from "@/hooks/useAPHeartbeats";
import WorkerMarker from "./WorkerMarker";
import { listAPs, listCCTVs, type APRecord, type CCTVRecord } from "@/services/floorService";

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
  const [outerSize, setOuterSize] = useState({ w: 0, h: 0 });

  const [hoveredZone, setHoveredZone] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const [aps, setAps] = useState<APRecord[]>([]);
  const [cctvs, setCctvs] = useState<CCTVRecord[]>([]);
  const [hoveredMarker, setHoveredMarker] = useState<{ label: string; x: number; y: number } | null>(null);

  const outerRef = useRef<HTMLDivElement>(null);
  const { zones } = useZones(buildingId, activeFloor?.id ?? null);
  const apStatuses = useAPHeartbeats();
  const scale = activeFloor?.scale_pixels_per_meter ?? null;

  useEffect(() => {
    if (!outerRef.current) return;
    const obs = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setOuterSize({ w: width, h: height });
    });
    obs.observe(outerRef.current);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    if (!buildingId || !activeFloor) { setAps([]); setCctvs([]); return; }
    listAPs(buildingId, activeFloor.id).then(setAps).catch(() => {});
    listCCTVs(buildingId, activeFloor.id).then(setCctvs).catch(() => {});
  }, [buildingId, activeFloor?.id]);

  // With w-full h-auto on the image the container height equals the image height,
  // so imageRect will always be {x:0, y:0, w, h}. The calculation stays for
  // correctness in case layout constraints ever cause letterboxing.
  const imageRect = useMemo(() => {
    if (!naturalSize || !outerSize.w || !outerSize.h) return null;
    const containerRatio = outerSize.w / outerSize.h;
    const imageRatio = naturalSize.w / naturalSize.h;
    let w: number, h: number, x: number, y: number;
    if (containerRatio > imageRatio) {
      h = outerSize.h; w = h * imageRatio;
      x = (outerSize.w - w) / 2; y = 0;
    } else {
      w = outerSize.w; h = w / imageRatio;
      x = 0; y = (outerSize.h - h) / 2;
    }
    return { x, y, w, h };
  }, [naturalSize, outerSize]);

  const toPct = (metres: number, axis: "x" | "y"): number => {
    if (!naturalSize || !scale) return 0;
    return ((metres * scale) / (axis === "x" ? naturalSize.w : naturalSize.h)) * 100;
  };

  const toPixel = (p: PositionRecord): { px: number; py: number } => {
    if (p.pixel_x != null && p.pixel_y != null) return { px: p.pixel_x, py: p.pixel_y };
    return { px: (p.x / MAP_W_M) * CANVAS_W, py: (p.y / MAP_H_M) * CANVAS_H };
  };

  if (!activeFloor) {
    return (
      <div className="flex items-center justify-center h-64 rounded-xl bg-s-surface border border-s-border text-s-muted">
        <p className="text-sm">No active floor plan</p>
      </div>
    );
  }

  return (
    <div ref={outerRef} className="relative w-full rounded-xl overflow-hidden border border-s-border bg-s-elevated shadow-sm">
      {/* Image — h-auto so the card height matches the floor plan aspect ratio exactly */}
      <img
        src={activeFloor.url}
        alt={activeFloor.name}
        className="w-full h-auto block"
        onLoad={(e) => {
          const img = e.currentTarget;
          setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
        }}
      />

      {/* Zone toggle — pinned to the outer card corner, always visible */}
      {zones.length > 0 && (
        <button
          onClick={(e) => { e.stopPropagation(); setShowZones((v) => !v); }}
          className="absolute top-2 right-2 z-20 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg font-mono text-[10px] tracking-widest transition-colors"
          style={{ backgroundColor: showZones ? "rgba(245,158,11,0.15)" : "rgba(0,0,0,0.45)", color: showZones ? "#f59e0b" : "rgba(255,255,255,0.7)" }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {showZones
              ? <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>
              : <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></>}
          </svg>
          ZONES
        </button>
      )}

      {/* All data overlays — positioned within the exact image area */}
      {imageRect && (
        <div
          className="absolute pointer-events-none"
          style={{ left: imageRect.x, top: imageRect.y, width: imageRect.w, height: imageRect.h }}
        >
          {/* Zone overlays */}
          {showZones && naturalSize && scale && zones.map((zone) => (
            <div
              key={zone.id}
              style={{
                position: "absolute",
                left: `${toPct(zone.x_min, "x")}%`,
                top: `${toPct(zone.y_min, "y")}%`,
                width: `${toPct(zone.x_max - zone.x_min, "x")}%`,
                height: `${toPct(zone.y_max - zone.y_min, "y")}%`,
                backgroundColor: zone.color,
                pointerEvents: "auto",
                cursor: "default",
              }}
              onMouseEnter={(e) => { setHoveredZone(`${zone.name}${zone.is_high_risk ? " ⚠" : ""}`); setTooltipPos({ x: e.clientX, y: e.clientY }); }}
              onMouseMove={(e) => setTooltipPos({ x: e.clientX, y: e.clientY })}
              onMouseLeave={() => setHoveredZone(null)}
            />
          ))}

          {/* AP markers */}
          {aps.map((ap) => {
            const status = apStatuses[ap.mac.toUpperCase()] ?? "unknown";
            const dotColor =
              status === "online"  ? "#22c55e" :
              status === "offline" ? "#ef4444" : "#6b7280";
            const label = `${ap.name} — ${ap.mac} — ${status}`;
            return (
              <div
                key={ap.id}
                className="absolute"
                style={{ left: `${ap.x_pct * 100}%`, top: `${ap.y_pct * 100}%`, transform: "translate(-50%, -50%)", pointerEvents: "auto", zIndex: 10 }}
                onMouseEnter={(e) => setHoveredMarker({ label, x: e.clientX, y: e.clientY })}
                onMouseMove={(e) => setHoveredMarker({ label, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setHoveredMarker(null)}
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>
                </svg>
                <span style={{ position: "absolute", bottom: -2, right: -2, width: 7, height: 7, borderRadius: "50%", background: dotColor, border: "1.5px solid var(--bg-base, #111)", display: "block" }} />
              </div>
            );
          })}

          {/* CCTV markers */}
          {cctvs.map((cctv) => (
            <div
              key={cctv.id}
              className="absolute"
              style={{ left: `${cctv.x_pct * 100}%`, top: `${cctv.y_pct * 100}%`, transform: "translate(-50%, -50%)", pointerEvents: "auto", zIndex: 10 }}
              onMouseEnter={(e) => setHoveredMarker({ label: cctv.name, x: e.clientX, y: e.clientY })}
              onMouseMove={(e) => setHoveredMarker({ label: cctv.name, x: e.clientX, y: e.clientY })}
              onMouseLeave={() => setHoveredMarker(null)}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
              </svg>
            </div>
          ))}

          {/* Worker markers */}
          <svg
            viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
            aria-label="Worker positions overlay"
          >
            {positions.map((p) => {
              const { px, py } = toPixel(p);
              return <WorkerMarker key={p.beacon_mac} position={p} px={px} py={py} />;
            })}
          </svg>

          {/* Calibration warning */}
          {!activeFloor.scale_pixels_per_meter && (
            <div className="absolute bottom-0 inset-x-0 flex items-center gap-2 px-4 py-2.5 bg-s-elevated/95 border-t border-s-border backdrop-blur-sm" style={{ pointerEvents: "auto" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-s-accent shrink-0">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <p className="font-mono text-[10px] text-s-muted tracking-wide">
                Floor plan not calibrated — worker positions may be inaccurate. Set scale in the <span className="text-s-text">Floor Plans</span> tab.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Zone tooltip */}
      {hoveredZone && typeof document !== "undefined" && createPortal(
        <div style={{ position: "fixed", left: tooltipPos.x + 12, top: tooltipPos.y - 8, background: "var(--bg-elevated)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "4px 10px", borderRadius: "6px", fontSize: "12px", pointerEvents: "none", zIndex: 9999, fontFamily: "IBM Plex Mono, monospace", whiteSpace: "nowrap" }}>
          {hoveredZone}
        </div>,
        document.body
      )}

      {/* Marker tooltip */}
      {hoveredMarker && typeof document !== "undefined" && createPortal(
        <div style={{ position: "fixed", left: hoveredMarker.x + 12, top: hoveredMarker.y - 8, background: "var(--bg-elevated)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "4px 10px", borderRadius: "6px", fontSize: "12px", pointerEvents: "none", zIndex: 9999, fontFamily: "IBM Plex Mono, monospace", whiteSpace: "nowrap" }}>
          {hoveredMarker.label}
        </div>,
        document.body
      )}
    </div>
  );
}
