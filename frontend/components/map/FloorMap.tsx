"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import { createPortal } from "react-dom";
import type { PositionRecord } from "@/types/position";
import type { FloorRecord } from "@/types/floor";
import { useZones } from "@/hooks/useZones";
import { useAPHeartbeats } from "@/hooks/useAPHeartbeats";
import { useCCTVHeartbeats } from "@/hooks/useCCTVHeartbeats";
import { useDashboardStore } from "@/store/dashboardStore";
import WorkerMarker from "./WorkerMarker";
import PatrolRouteOverlay from "./PatrolRouteOverlay";
import { subscribeToAPs, subscribeToCCTVs, subscribeToPatrolLogs, type APRecord, type CCTVRecord } from "@/services/floorService";
import type { PatrolLogRecord } from "@/types/patrolLog";

// Bounded read (Prompt 114) — most-recent-200 across all floors/guards, since
// there's no backend endpoint or floor_id field to filter this server-side.
// Filtered down to this floor's checkpoints client-side below.
const PATROL_LOG_FETCH_LIMIT = 200;

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

// A live marker refreshes every ~2s (EMIT_MIN_INTERVAL_S 1.8 + 2s ingest buffer).
// 12s ≈ 6 missed cycles — confidently gone without flickering on a couple of
// dropped AP POSTs. Tune here after watching the demo.
const STALE_POSITION_MS = 12_000;

function WorkerInfoBlock({ position }: { position: PositionRecord }) {
  const displayName = position.label || position.person_id;
  const typeLabel   = WORKER_TYPE_LABEL[position.person_type] ?? position.person_type;
  const fill        = WORKER_TYPE_COLOUR[position.person_type] ?? "var(--text-secondary)";

  return (
    <div>
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
      {position.is_approximate && position.radius_m != null && (
        <div style={{ fontSize: 10, fontFamily: "IBM Plex Mono, monospace", color: "var(--text-secondary)", opacity: 0.7 }}>
          ~approximate · ±{position.radius_m.toFixed(1)}m (single AP)
        </div>
      )}
    </div>
  );
}

// Renders one block per beacon under the cursor — plural because overlapping
// circles (most commonly: multiple beacons anchored to the same single AP)
// can mean more than one beacon is "here" at once. See handleMapMouseMove.
function WorkerTooltip({ positions, x, y }: { positions: PositionRecord[]; x: number; y: number }) {
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
      {positions.map((position, i) => (
        <div
          key={position.beacon_mac}
          style={i > 0 ? { marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border)" } : undefined}
        >
          <WorkerInfoBlock position={position} />
        </div>
      ))}
    </div>
  );
}

export default function FloorMap({ positions, buildingId, activeFloor }: Props) {
  // Zone-overlay toggle lives in the Zustand store so the user's choice survives
  // navigating away to /dashboard/alerts and back (the dashboard layout's
  // key={pathname} on <main> forces this component to remount on every route change).
  const showZones = useDashboardStore((s) => s.showZones);
  const toggleShowZones = useDashboardStore((s) => s.toggleShowZones);
  const showPatrolRoute = useDashboardStore((s) => s.showPatrolRoute);
  const toggleShowPatrolRoute = useDashboardStore((s) => s.toggleShowPatrolRoute);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);
  const [outerSize, setOuterSize] = useState({ w: 0, h: 0 });

  const [hoveredZone, setHoveredZone] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

  const [aps, setAps] = useState<APRecord[]>([]);
  const [cctvs, setCctvs] = useState<CCTVRecord[]>([]);
  const [patrolLogs, setPatrolLogs] = useState<PatrolLogRecord[]>([]);
  const [hoveredMarker, setHoveredMarker] = useState<{ label: string; x: number; y: number } | null>(null);
  // Every beacon whose marker/circle currently contains the cursor — not just
  // one. Computed in JS (handleMapMouseMove) rather than via per-marker DOM
  // hover, because the DOM can only ever deliver a mouse event to one topmost
  // element at a pixel; two overlapping beacons (e.g. both anchored to the
  // same AP) would otherwise silently hide one another.
  const [hoveredWorkers, setHoveredWorkers] = useState<{ positions: PositionRecord[]; x: number; y: number } | null>(null);

  const outerRef = useRef<HTMLDivElement>(null);
  const workerSvgRef = useRef<SVGSVGElement>(null);
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
    const unsubAPs = subscribeToAPs(buildingId, activeFloor.id, setAps);
    const unsubCCTVs = subscribeToCCTVs(buildingId, activeFloor.id, setCctvs);
    return () => { unsubAPs(); unsubCCTVs(); };
  }, [buildingId, activeFloor?.id]);

  // One bounded, global subscription — patrol_logs has no floor_id field to
  // scope this server-side (114a recon), so this pulls the N most recent
  // across every floor/guard and gets filtered down to this floor just below.
  useEffect(() => {
    const unsub = subscribeToPatrolLogs(PATROL_LOG_FETCH_LIMIT, setPatrolLogs);
    return unsub;
  }, []);

  // checkpoint_id is an AP mac, patrol_route is AP ids — join on mac, not index.
  const floorPatrolLogs = useMemo(() => {
    if (aps.length === 0) return [];
    const floorMacs = new Set(aps.map((a) => a.mac.toUpperCase()));
    return patrolLogs.filter((l) => floorMacs.has(l.checkpoint_id.toUpperCase()));
  }, [patrolLogs, aps]);

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

  // Drop markers whose backend timestamp has gone stale — a departed beacon's
  // last /positions record otherwise lingers on the map forever (nothing deletes
  // the RTDB node). Compared against the freshest marker in the batch, not
  // browser-now, so client/server clock skew doesn't drop live markers.
  const livePositions = useMemo(() => {
    if (positions.length === 0) return positions;

    const times = positions.map((p) => {
      const t = Date.parse(p.timestamp);
      return Number.isNaN(t) ? Infinity : t;   // malformed → treat as fresh, never hide
    });
    const freshest = Math.max(...times);

    // All-stale backstop: if even the freshest marker is older than the window
    // relative to the wall clock, everyone has left — clear them all. This is the
    // ONLY place browser-now is used.
    if (freshest !== Infinity && Date.now() - freshest > STALE_POSITION_MS) {
      return [];
    }

    return positions.filter((_, i) => freshest - times[i] <= STALE_POSITION_MS);
  }, [positions]);

  const toPct = (metres: number, axis: "x" | "y"): number => {
    if (!naturalSize || !scale) return 0;
    return ((metres * scale) / (axis === "x" ? naturalSize.w : naturalSize.h)) * 100;
  };

  const toPixel = (p: PositionRecord): { px: number; py: number } => {
    if (p.pixel_x != null && p.pixel_y != null) return { px: p.pixel_x, py: p.pixel_y };
    if (naturalSize && scale) return { px: p.x * scale, py: p.y * scale };
    return { px: 0, py: 0 };
  };

  // Minimum hit radius in SVG px — matches the visual halo (r=12) drawn around
  // every worker dot, so exact-position beacons (no approximate circle) stay
  // comfortably hoverable too, not just a 7px pinpoint.
  const MIN_HIT_RADIUS_PX = 12;

  // Attached on the outer container (not the worker <svg>, which is
  // pointer-events:none) so it reliably fires no matter what's visually on
  // top at that pixel — a zone, an AP icon, or empty floor plan. Checks every
  // live beacon's distance from the cursor directly in JS rather than relying
  // on DOM hover, which only ever hands the event to one topmost element.
  const handleMapMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!workerSvgRef.current || !naturalSize) { setHoveredWorkers(null); return; }
    const rect = workerSvgRef.current.getBoundingClientRect();
    if (!rect.width || !rect.height) { setHoveredWorkers(null); return; }

    const svgX = ((e.clientX - rect.left) / rect.width) * naturalSize.w;
    const svgY = ((e.clientY - rect.top) / rect.height) * naturalSize.h;

    const hits = livePositions.filter((p) => {
      const { px, py } = toPixel(p);
      const hitRadius =
        p.is_approximate && p.radius_m != null && scale
          ? Math.max(p.radius_m * scale, MIN_HIT_RADIUS_PX)
          : MIN_HIT_RADIUS_PX;
      const dx = svgX - px, dy = svgY - py;
      return dx * dx + dy * dy <= hitRadius * hitRadius;
    });

    setHoveredWorkers(hits.length > 0 ? { positions: hits, x: e.clientX, y: e.clientY } : null);
  };

  if (!activeFloor) {
    return (
      <div className="flex items-center justify-center h-64 rounded-xl bg-s-surface border border-s-border text-s-muted">
        <p className="text-sm">No active floor plan</p>
      </div>
    );
  }

  return (
    <div
      ref={outerRef}
      className="relative w-full rounded-xl overflow-hidden border border-s-border bg-s-elevated shadow-sm"
      onMouseMove={handleMapMouseMove}
      onMouseLeave={() => setHoveredWorkers(null)}
    >
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

      {/* Zone / patrol-route toggles — pinned to the outer card corner, always visible */}
      <div className="absolute top-2 right-2 z-20 flex items-center gap-1.5">
        {activeFloor.patrol_enabled && (activeFloor.patrol_route?.length ?? 0) > 0 && (
          <button
            onClick={(e) => { e.stopPropagation(); toggleShowPatrolRoute(); }}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg font-mono text-[10px] tracking-widest transition-colors"
            style={{ backgroundColor: showPatrolRoute ? "rgba(245,158,11,0.15)" : "rgba(0,0,0,0.45)", color: showPatrolRoute ? "#f59e0b" : "rgba(255,255,255,0.7)" }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8 7l8 10"/>
            </svg>
            ROUTE
          </button>
        )}
        {zones.length > 0 && (
          <button
            onClick={(e) => { e.stopPropagation(); toggleShowZones(); }}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg font-mono text-[10px] tracking-widest transition-colors"
            style={{ backgroundColor: showZones ? "rgba(245,158,11,0.15)" : "rgba(0,0,0,0.45)", color: showZones ? "#f59e0b" : "rgba(255,255,255,0.7)" }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              {showZones
                ? <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>
                : <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></>}
            </svg>
            ZONES
          </button>
        )}
      </div>

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
            const status = apStatuses[ap.mac.toUpperCase()]?.status ?? "unknown";
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
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="13"/><circle cx="12" cy="12" r="2.2" fill="var(--accent)" stroke="none"/><path d="M7.5 9.2a4 4 0 0 0 0 5.6"/><path d="M5 7a7.5 7.5 0 0 0 0 10"/><path d="M16.5 9.2a4 4 0 0 1 0 5.6"/><path d="M19 7a7.5 7.5 0 0 1 0 10"/>
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
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 8 Q4 4 8 4 L22 4 Q28 6 28 10 Q28 14 22 16 L8 16 Q4 16 4 12 Z"/><ellipse cx="5.5" cy="10" rx="3.5" ry="4.5"/><circle cx="5.5" cy="10" r="1.5" fill="var(--danger)" stroke="none"/><path d="M20 16 L19 20 L15 20"/><rect x="13" y="19" width="4" height="6" rx="1"/><rect x="17" y="20" width="5" height="8" rx="1"/>
                </svg>
                {dotColor && (
                  <span style={{ position: "absolute", bottom: -2, right: -2, width: 7, height: 7, borderRadius: "50%", background: dotColor, border: "1.5px solid var(--bg-base, #111)", display: "block" }} />
                )}
              </div>
            );
          })}

          {/* Patrol route overlay — rendered before the worker svg so the live
              position dot stays visually on top of the static route/checkpoints. */}
          {showPatrolRoute && activeFloor.patrol_enabled && (activeFloor.patrol_route?.length ?? 0) > 0 && (
            <PatrolRouteOverlay
              aps={aps}
              route={activeFloor.patrol_route ?? []}
              logs={floorPatrolLogs}
              positions={livePositions}
              naturalSize={naturalSize}
              scale={scale}
            />
          )}

          {/* Worker markers — purely visual; hover is computed in handleMapMouseMove */}
          <svg
            ref={workerSvgRef}
            viewBox={naturalSize ? `0 0 ${naturalSize.w} ${naturalSize.h}` : "0 0 1 1"}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
            aria-label="Worker positions overlay"
          >
            {naturalSize && livePositions.map((p) => {
              const { px, py } = toPixel(p);
              return (
                <WorkerMarker
                  key={p.beacon_mac}
                  position={p}
                  px={px}
                  py={py}
                  scale={scale}
                />
              );
            })}
          </svg>

          {/* Calibration warning */}
          {!activeFloor.scale_pixels_per_meter && (
            <div className="absolute bottom-0 inset-x-0 flex items-center gap-2 px-4 py-2.5 bg-s-elevated/95 border-t border-s-border backdrop-blur-sm" style={{ pointerEvents: "auto" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-s-accent shrink-0">
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

      {/* Worker tooltip — one block per beacon under the cursor */}
      {hoveredWorkers && typeof document !== "undefined" && createPortal(
        <WorkerTooltip positions={hoveredWorkers.positions} x={hoveredWorkers.x} y={hoveredWorkers.y} />,
        document.body
      )}
    </div>
  );
}
