"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { APRecord } from "@/services/floorService";
import type { PatrolLogRecord } from "@/types/patrolLog";
import type { PositionRecord } from "@/types/position";
import { sortPatrolLogsDeterministically } from "@/utils/patrolLogOrder";

interface Props {
  aps: APRecord[];
  route: string[];               // ordered AP ids, from FloorRecord.patrol_route
  logs: PatrolLogRecord[];       // already filtered to this floor's checkpoint macs by the caller
  positions: PositionRecord[];   // all live positions; guard matching happens here. Pass [] for historical review — no position can ever be "in progress".
  naturalSize: { w: number; h: number } | null;
  scale: number | null;
  // Backend's PATROL_PROXIMITY_RADIUS_M, crossed via FloorRecord (Prompt 117)
  // instead of a hardcoded frontend copy — single source of truth.
  proximityRadiusM: number;
  // Review-mode detail (Prompt 115): direction arrows per segment, an arrival
  // time label at each visited/short-dwell checkpoint, and dwell encoded in
  // marker radius. Off by default so the live dashboard overlay (Prompt 114,
  // already validated) renders byte-for-byte as it did before this prop existed.
  showDetails?: boolean;
  // Dashboard mode (post-118): just the faint connecting line between
  // checkpoints, no checkpoint state markers, no live-position marker, no
  // guard/cycle grouping. The full tracking overlay stays on the patrol
  // report page only. Takes priority over showDetails.
  lineOnly?: boolean;
}

// Dwell -> marker radius, only meaningful where a real dwell was measured
// (visited/short-dwell). Bounded so one long stop can't dwarf the map.
const BASE_RADIUS = 10;
const MAX_RADIUS = 16;
function dwellRadius(dwellSeconds: number): number {
  return Math.min(MAX_RADIUS, BASE_RADIUS + dwellSeconds / 10);
}

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
  proximityRadiusM: number,
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
    if (Math.sqrt(dx * dx + dy * dy) <= proximityRadiusM) return "in_progress";
  }
  return "pending";
}

export default function PatrolRouteOverlay({ aps, route, logs, positions, naturalSize, scale, proximityRadiusM, showDetails = false, lineOnly = false }: Props) {
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

  // Deterministic ordering (Prompt 121) before the mac-keyed map below —
  // relying on Firestore/JS's arbitrary tie-break on expected_arrival would
  // let this map's construction order (and thus which log wins on a
  // duplicate-mac collision) vary between loads.
  const sortedCycleLogs = useMemo(
    () => sortPatrolLogsDeterministically(currentCycle?.logs ?? [], routeAps),
    [currentCycle, routeAps],
  );

  const logByMac = useMemo(() => {
    const m = new Map<string, PatrolLogRecord>();
    for (const log of sortedCycleLogs) {
      m.set(log.checkpoint_id.toUpperCase(), log);
    }
    return m;
  }, [sortedCycleLogs]);

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

  if (lineOnly) {
    // Dashboard mode only (Prompt 118 §1) — vague connective guide, not a
    // rendered path taken: muted border colour, thin stroke, low opacity.
    return (
      <svg
        viewBox={`0 0 ${naturalSize.w} ${naturalSize.h}`}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
        aria-label="Patrol route"
      >
        <polyline
          points={polylinePoints}
          fill="none"
          stroke="var(--border)"
          strokeWidth={1}
          strokeDasharray="6 5"
          opacity={0.35}
        />
      </svg>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${naturalSize.w} ${naturalSize.h}`}
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
      aria-label="Patrol route overlay"
    >
        {/* Report/review mode — original bolder dashed guide, unchanged by
            Prompt 118's dashboard-only subtle-line request. */}
        <polyline
          points={polylinePoints}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={2}
          strokeDasharray="6 5"
          opacity={0.6}
        />

        {/* Direction arrows — one per segment, at its midpoint. Deterministic
            geometry from known checkpoint coordinates, not a rendered "path
            taken": there is no position history, only straight segments
            between checkpoints (see PatrolRouteOverlay's callers). */}
        {showDetails && points.slice(1).map((to, i) => {
          const from = points[i];
          const mx = (from.px + to.px) / 2;
          const my = (from.py + to.py) / 2;
          const angleDeg = Math.atan2(to.py - from.py, to.px - from.px) * (180 / Math.PI);
          return (
            <polygon
              key={`arrow-${i}`}
              points="-5,-4 5,0 -5,4"
              fill="var(--accent)"
              opacity={0.85}
              transform={`translate(${mx},${my}) rotate(${angleDeg})`}
            />
          );
        })}

        {routeAps.map((ap, idx) => {
          const log = logByMac.get(ap.mac.toUpperCase());
          const state = checkpointState(log, livePosition, ap, proximityRadiusM);
          const { px, py } = points[idx];
          const hasRealDwell = showDetails && log && log.actual_arrival !== null;
          const radius = hasRealDwell ? dwellRadius(log!.dwell_time_seconds) : BASE_RADIUS;
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
              {showDetails && log?.actual_arrival && (
                <text
                  x={px} y={py + radius + 14}
                  textAnchor="middle"
                  fontSize={9} fontFamily="IBM Plex Mono, monospace"
                  fill="var(--text-primary)"
                >
                  {new Date(log.actual_arrival).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </text>
              )}
            </g>
          );
        })}

        {/* Guard's real live position riding on the route (Prompt 118 §3) —
            the actual solved x_m/y_m, not snapped to the nearest checkpoint
            node. Shows correctly between checkpoints when that's genuinely
            where they are. positions=[] on the historical report page means
            livePosition is always null there, so this never renders in
            review mode. */}
        {livePosition && (
          <g style={{ pointerEvents: "none" }}>
            <circle cx={livePosition.x * scale} cy={livePosition.y * scale} r={9} fill="var(--accent)" fillOpacity={0.18} />
            <circle cx={livePosition.x * scale} cy={livePosition.y * scale} r={5} fill="var(--accent)" stroke="var(--bg-base)" strokeWidth={2} />
          </g>
      )}
    </svg>
  );
}
