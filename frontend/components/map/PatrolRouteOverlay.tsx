"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { APRecord } from "@/services/floorService";
import type { PatrolLogRecord } from "@/types/patrolLog";
import type { PositionRecord } from "@/types/position";

interface Props {
  aps: APRecord[];
  route: string[];               // ordered AP ids, from FloorRecord.patrol_route
  logs: PatrolLogRecord[];       // already filtered to this floor's checkpoint macs by the caller
  positions: PositionRecord[];   // all live positions; guard matching happens here. Pass [] for historical review — no position can ever be "in progress".
  naturalSize: { w: number; h: number } | null;
  scale: number | null;
}

// Fixed marker radius for the live dashboard overlay.
const BASE_RADIUS = 10;

type CheckpointState = "visited" | "short_dwell" | "missed" | "in_progress" | "pending";

const STATE_STROKE: Record<CheckpointState, string> = {
  visited: "var(--success)",
  short_dwell: "var(--warning)",
  missed: "var(--danger)",
  in_progress: "var(--accent)",
  pending: "var(--text-secondary)",
};

const STATE_FILL: Record<CheckpointState, string> = {
  visited: "var(--success)",
  short_dwell: "var(--warning)",
  missed: "var(--danger)",
  in_progress: "var(--text-secondary)",   // pending fill + accent ring, per spec
  pending: "var(--text-secondary)",
};

// Mirrors backend PATROL_PROXIMITY_RADIUS_M (config/settings.py). No settings
// endpoint exposes this value live — only man_down_minutes/collision_distance_m
// are DB-backed — so this is a frontend-side duplicate of the backend default,
// same tradeoff MIN_DWELL_SECONDS-family constants already carry. If the
// backend env var changes, this needs updating by hand.
const PATROL_PROXIMITY_RADIUS_M = 1.0;

function cycleKeyOf(log: PatrolLogRecord): string {
  // Historical simulation logs predate cycle_id (Prompt 110) and have none —
  // shift_id was the pre-existing "one lap" grouping for that era's data, so
  // fall back to it rather than losing the ability to group old cycles at all.
  return (log.cycle_id && log.cycle_id !== "") ? log.cycle_id : (log.shift_id || "unknown");
}

function checkpointState(
  log: PatrolLogRecord | undefined,
  livePosition: PositionRecord | null,
  ap: APRecord,
): CheckpointState {
  if (log) {
    if (log.actual_arrival === null) return "missed";
    return log.compliant ? "visited" : "short_dwell";
  }
  // No log this cycle. Close-out is departure-triggered (patrol_tracker_service.py),
  // so the checkpoint the guard is CURRENTLY standing on always lacks a log —
  // without this branch it would render identically to "not yet reached," which
  // is simply wrong while the guard is right there.
  if (livePosition) {
    const dx = livePosition.x - ap.x_m;
    const dy = livePosition.y - ap.y_m;
    if (Math.sqrt(dx * dx + dy * dy) <= PATROL_PROXIMITY_RADIUS_M) return "in_progress";
  }
  return "pending";
}

export default function PatrolRouteOverlay({ aps, route, logs, positions, naturalSize, scale }: Props) {
  const [selectedGuardId, setSelectedGuardId] = useState<string | null>(null);
  const warnedMissingIds = useRef<Set<string>>(new Set());

  const apById = useMemo(() => new Map(aps.map((a) => [a.id, a])), [aps]);

  // Resolve route ids -> AP records, in order. A route referencing a deleted
  // AP must not break the map — skip it, log once per id.
  const routeAps = useMemo(() => {
    const resolved: APRecord[] = [];
    for (const id of route) {
      const ap = apById.get(id);
      if (ap) {
        resolved.push(ap);
      } else if (!warnedMissingIds.current.has(id)) {
        warnedMissingIds.current.add(id);
        console.warn(`[PatrolRouteOverlay] patrol_route references unknown AP id "${id}" — skipped`);
      }
    }
    return resolved;
  }, [route, apById]);

  // Every (guard, cycle) group present in the floor-filtered logs, with its
  // start time (MIN expected_arrival — the field that's always populated,
  // including on skip records, unlike actual_arrival). Cycle start = the
  // first checkpoint's expected_arrival, which equals cycle_started_at by
  // construction (patrol_tracker_service.py _close_visit). MAX(expected_arrival)
  // is deliberately not used to order cycles — the last checkpoint can
  // legitimately have no log at all (the never-written case), which would make
  // that endpoint unstable.
  const cycleGroups = useMemo(() => {
    const groups = new Map<string, { guardId: string; start: string; logs: PatrolLogRecord[] }>();
    for (const log of logs) {
      const key = `${log.guard_id}::${cycleKeyOf(log)}`;
      let g = groups.get(key);
      if (!g) {
        g = { guardId: log.guard_id, start: log.expected_arrival, logs: [] };
        groups.set(key, g);
      }
      if (log.expected_arrival < g.start) g.start = log.expected_arrival;
      g.logs.push(log);
    }
    return groups;
  }, [logs]);

  const distinctGuardIds = useMemo(
    () => Array.from(new Set(Array.from(cycleGroups.values()).map((g) => g.guardId))).sort(),
    [cycleGroups],
  );

  // Default guard: the guard of the single most recent cycle across everyone
  // on this floor. Falls back to whichever guard has a live position here if
  // there are no logs yet at all (cold start, nothing closed a checkpoint yet).
  const defaultGuardId = useMemo(() => {
    let best: { guardId: string; start: string } | null = null;
    for (const g of cycleGroups.values()) {
      if (!best || g.start > best.start) best = { guardId: g.guardId, start: g.start };
    }
    if (best) return best.guardId;
    const liveGuard = positions.find((p) => p.person_type === "guard");
    return liveGuard?.person_id ?? null;
  }, [cycleGroups, positions]);

  useEffect(() => {
    // Only steer the selection when it's unset or no longer valid (e.g. the
    // previously-selected guard has no data on this floor anymore) — an
    // explicit user pick via the selector must survive new logs arriving.
    if (selectedGuardId === null || (distinctGuardIds.length > 0 && !distinctGuardIds.includes(selectedGuardId))) {
      setSelectedGuardId(defaultGuardId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultGuardId]);

  const activeGuardId = selectedGuardId ?? defaultGuardId;

  const currentCycle = useMemo(() => {
    if (!activeGuardId) return null;
    let best: { start: string; logs: PatrolLogRecord[] } | null = null;
    for (const g of cycleGroups.values()) {
      if (g.guardId !== activeGuardId) continue;
      if (!best || g.start > best.start) best = { start: g.start, logs: g.logs };
    }
    return best;
  }, [cycleGroups, activeGuardId]);

  const logByMac = useMemo(() => {
    const m = new Map<string, PatrolLogRecord>();
    for (const log of currentCycle?.logs ?? []) {
      m.set(log.checkpoint_id.toUpperCase(), log);
    }
    return m;
  }, [currentCycle]);

  const livePosition = useMemo(
    () => positions.find((p) => p.person_type === "guard" && p.person_id === activeGuardId) ?? null,
    [positions, activeGuardId],
  );

  // Calibration gate, matching FloorMap.tsx's own convention (:130, :370) —
  // no scale means no metre->pixel conversion, so there's nothing safe to draw.
  if (!naturalSize || !scale || routeAps.length === 0) return null;

  const toPixel = (ap: APRecord) => ({ px: ap.x_m * scale, py: ap.y_m * scale });
  const points = routeAps.map(toPixel);
  const polylinePoints = points.map((p) => `${p.px},${p.py}`).join(" ");

  const loggedCount = routeAps.filter((ap) => logByMac.has(ap.mac.toUpperCase())).length;

  return (
    <>
      <svg
        viewBox={`0 0 ${naturalSize.w} ${naturalSize.h}`}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
        aria-label="Patrol route overlay"
      >
        <polyline
          points={polylinePoints}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={2}
          strokeDasharray="6 5"
          opacity={0.6}
        />

        {routeAps.map((ap, idx) => {
          const log = logByMac.get(ap.mac.toUpperCase());
          const state = checkpointState(log, livePosition, ap);
          const { px, py } = points[idx];
          const radius = BASE_RADIUS;
          return (
            <g key={ap.id}>
              {state === "in_progress" && (
                <circle cx={px} cy={py} r={radius + 4} fill="none" stroke="var(--accent)" strokeWidth={2} opacity={0.8} />
              )}
              <circle cx={px} cy={py} r={radius} fill={STATE_FILL[state]} stroke={STATE_STROKE[state]} strokeWidth={2} />
              <text
                x={px} y={py}
                textAnchor="middle" dominantBaseline="central"
                fontSize={10} fontFamily="IBM Plex Mono, monospace" fontWeight={700}
                fill="var(--bg-base)"
              >
                {idx + 1}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Cycle info + guard selector — HTML, not SVG, matching FloorMap's own
          badge/tooltip convention (positioned divs over the image, not canvas text). */}
      <div
        className="absolute top-2 left-2 z-20 flex items-center gap-2 px-2.5 py-1.5 rounded-lg font-mono text-[10px] tracking-wide"
        style={{ backgroundColor: "rgba(0,0,0,0.45)", color: "rgba(255,255,255,0.85)", pointerEvents: "auto" }}
      >
        {distinctGuardIds.length > 1 && (
          <select
            value={activeGuardId ?? ""}
            onChange={(e) => setSelectedGuardId(e.target.value)}
            className="bg-transparent border border-white/20 rounded px-1 py-0.5 text-[10px]"
            style={{ colorScheme: "dark" }}
          >
            {distinctGuardIds.map((gid) => (
              <option key={gid} value={gid} style={{ color: "#000" }}>{gid}</option>
            ))}
          </select>
        )}
        {currentCycle ? (
          <span>
            {activeGuardId} · started {new Date(currentCycle.start).toLocaleTimeString()} ·{" "}
            {loggedCount}/{routeAps.length} checkpoints
          </span>
        ) : activeGuardId ? (
          <span>{activeGuardId} · patrol not yet started</span>
        ) : (
          <span>No patrol activity yet</span>
        )}
      </div>
    </>
  );
}
