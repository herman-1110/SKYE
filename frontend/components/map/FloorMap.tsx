"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import type { PositionRecord } from "@/types/position";
import type { FloorRecord } from "@/types/floor";
import { useZones } from "@/hooks/useZones";
import { useAPHeartbeats } from "@/hooks/useAPHeartbeats";
import { useCCTVHeartbeats } from "@/hooks/useCCTVHeartbeats";
import WorkerMarker from "./WorkerMarker";
import { listAPs, listCCTVs, type APRecord, type CCTVRecord } from "@/services/floorService";

interface Props {
  positions: PositionRecord[];
  buildingId: string | null;
  activeFloor: FloorRecord | null;
}


const WORKER_TYPE_LABEL: Record<string, string> = {
  guard:    "Guard",
  worker:   "Worker",
  forklift: "Forklift",
};

const WORKER_TYPE_COLOUR: Record<string, string> = {
  guard:    "var(--success)",
  worker:   "var(--info)",
  forklift: "var(--warning)",
};

function WorkerTooltip({ position, x, y }: { position: PositionRecord; x: number; y: number }) {
  const displayName = position.label || position.person_id;
  const typeLabel   = WORKER_TYPE_LABEL[position.person_type] ?? position.person_type;
  const fill        = WORKER_TYPE_COLOUR[position.person_type] ?? "var(--text-secondary)";

  return (
    <div
      style={{
        position: "fixed",
        left: x + 14,
        top: y - 48,
        zIndex: 9999,
        pointerEvents: "none",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: "10px",
        padding: "8px 12px",
        minWidth: 160,
        boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
        fontFamily: "IBM Plex Sans, sans-serif",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ width: 8, height: 8, borderRadius: "50%", background: fill, flexShrink: 0, display: "inline-block" }} />
        <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 120 }}>
          {displayName}
        </span>
        <span style={{ flexShrink: 0, padding: "1px 7px", borderRadius: 99, fontSize: 10, fontFamily: "IBM Plex Mono, monospace", background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text-secondary)", marginLeft: "auto" }}>
          {typeLabel}
        </span>
      </div>
      {position.zone && (
        <div style={{ fontSize: 11, fontFamily: "IBM Plex Mono, monospace", color: "var(--text-secondary)", marginBottom: 2 }}>
          {position.zone}
        </div>
      )}
      <div style={{ fontSize: 10, fontFamily: "IBM Plex Mono, monospace", color: "var(--text-secondary)", opacity: 0.7 }}>
        {position.x.toFixed(1)}m, {position.y.toFixed(1)}m
      </div>
    </div>
  );
}

export default function FloorMap({ positions, buildingId, activeFloor }: Props) {
  const [showZones, setShowZones] = useState(true);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [outerSize, setOuterSize] = useState({ w: 0, h: 0 });

  const [hoveredZone, setHoveredZone] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const [aps, setAps] = useState<APRecord[]>([]);
  const [cctvs, setCctvs] = useState<CCTVRecord[]>([]);
  const [hoveredMarker, setHoveredMarker] = useState<{ label: string; x: number; y: number } | null>(null);
  const [hoveredWorker, setHoveredWorker] = useState<{ position: PositionRecord; x: number; y: number } | null>(null);

  const outerRef = useRef<HTMLDivElement>(null);
  const { zones } = useZones(buildingId, activeFloor?.id ?? null);
  const apStatuses = useAPHeartbeats();
  const cctvStatuses = useCCTVHeartbeats();
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
    if (naturalSize && scale) return { px: p.x * scale, py: p.y * scale };
    return { px: 0, py: 0 };
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
          {cctvs.map((cctv) => {
            const status = cctv.mac ? (cctvStatuses[cctv.mac.toUpperCase()] ?? "offline") : null;
            const dotColor = status === "online" ? "#22c55e" : status === "offline" ? "#ef4444" : null;
            const label = cctv.mac ? `${cctv.name} — ${cctv.mac} — ${status}` : cctv.name;
            return (
              <div
                key={cctv.id}
                className="absolute"
                style={{ left: `${cctv.x_pct * 100}%`, top: `${cctv.y_pct * 100}%`, transform: "translate(-50%, -50%)", pointerEvents: "auto", zIndex: 10 }}
                onMouseEnter={(e) => setHoveredMarker({ label, x: e.clientX, y: e.clientY })}
                onMouseMove={(e) => setHoveredMarker({ label, x: e.clientX, y: e.clientY })}
                onMouseLeave={() => setHoveredMarker(null)}
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                </svg>
                {dotColor && (
                  <span style={{ position: "absolute", bottom: -2, right: -2, width: 7, height: 7, borderRadius: "50%", background: dotColor, border: "1.5px solid var(--bg-base, #111)", display: "block" }} />
                )}
              </div>
            );
          })}

          {/* Worker markers */}
          <svg
            viewBox={naturalSize ? `0 0 ${naturalSize.w} ${naturalSize.h}` : "0 0 1 1"}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
            aria-label="Worker positions overlay"
          >
            {naturalSize && positions.map((p) => {
              const { px, py } = toPixel(p);
              return (
                <WorkerMarker
                  key={p.beacon_mac}
                  position={p}
                  px={px}
                  py={py}
                  onHover={setHoveredWorker}
                />
              );
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

      {/* Worker tooltip */}
      {hoveredWorker && typeof document !== "undefined" && createPortal(
        <WorkerTooltip position={hoveredWorker.position} x={hoveredWorker.x} y={hoveredWorker.y} />,
        document.body
      )}
    </div>
  );
}
