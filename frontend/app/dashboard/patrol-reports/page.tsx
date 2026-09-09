"use client";
import { useEffect, useMemo, useState } from "react";
import { useBuildings } from "@/hooks/useBuildings";
import { useFloors } from "@/hooks/useFloors";
import {
  subscribeToAPs,
  subscribeToPatrolLogs,
  subscribeToPatrolLogsByGuard,
  type APRecord,
} from "@/services/floorService";
import type { PatrolLogRecord } from "@/types/patrolLog";
import SelectDropdown from "@/components/shared/SelectDropdown";
import PatrolRouteOverlay from "@/components/map/PatrolRouteOverlay";
import { sortPatrolLogsDeterministically } from "@/utils/patrolLogOrder";

// Bounded reads throughout (Prompt 115) — no unbounded getDocs() anywhere.
// DISCOVERY_LOG_LIMIT: enough of the most-recent global activity to derive
// which guards have walked THIS floor at all, for the guard selector.
// GUARD_LOG_LIMIT: one guard's own full log history, once selected — scoped
// by guard_id server-side (composite index, see firestore.indexes.json), so
// this can be far larger without pulling in every other guard's data too.
const DISCOVERY_LOG_LIMIT = 500;
const GUARD_LOG_LIMIT = 1000;

interface Cycle {
  key: string;             // cycle_id, or shift_id fallback for pre-110 logs
  start: string;           // MIN(expected_arrival) in the group
  logs: PatrolLogRecord[];
}

// Historical simulation logs predate cycle_id (Prompt 110) and have none —
// shift_id was the pre-existing "one lap" grouping for that era, so fall back
// to it. Mirrors PatrolRouteOverlay's own cycleKeyOf exactly (114a/115 recon).
function cycleKeyOf(log: PatrolLogRecord): string {
  return log.cycle_id && log.cycle_id !== "" ? log.cycle_id : (log.shift_id || "unknown");
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

type RowStatus = "Compliant" | "Short dwell" | "Missed" | "No record";

export default function PatrolReportsPage() {
  const { buildings } = useBuildings();
  const [buildingId, setBuildingId] = useState<string | null>(null);
  const { floors } = useFloors(buildingId);
  const [floorId, setFloorId] = useState<string | null>(null);

  const [aps, setAps] = useState<APRecord[]>([]);
  const [naturalSize, setNaturalSize] = useState<{ w: number; h: number } | null>(null);

  const [discoveryLogs, setDiscoveryLogs] = useState<PatrolLogRecord[]>([]);
  const [guardId, setGuardId] = useState<string | null>(null);
  const [guardLogs, setGuardLogs] = useState<PatrolLogRecord[]>([]);
  const [cycleKey, setCycleKey] = useState<string | null>(null);
  // Bumped by the refresh button (Prompt 118 §4) to force a clean
  // unsubscribe/resubscribe of the guard-scoped query below. The query is
  // already a live onSnapshot subscription, so a new cycle should already
  // appear on its own — this is a manual "definitely current" affordance,
  // not the only path to freshness.
  const [refreshKey, setRefreshKey] = useState(0);

  const activeFloor = floors.find((f) => f.id === floorId) ?? null;

  // Auto-select first building, then its active floor (or first floor).
  useEffect(() => {
    if (buildings.length > 0 && !buildingId) setBuildingId(buildings[0].id);
  }, [buildings, buildingId]);

  useEffect(() => {
    if (floors.length === 0) { setFloorId(null); return; }
    if (floorId && floors.some((f) => f.id === floorId)) return;
    setFloorId((floors.find((f) => f.is_active) ?? floors[0]).id);
  }, [floors, floorId]);

  useEffect(() => {
    setNaturalSize(null);
    if (!buildingId || !floorId) { setAps([]); return; }
    return subscribeToAPs(buildingId, floorId, setAps);
  }, [buildingId, floorId]);

  // Discovery window: derive which guards have walked this floor at all.
  useEffect(() => subscribeToPatrolLogs(DISCOVERY_LOG_LIMIT, setDiscoveryLogs), []);

  const floorMacs = useMemo(() => new Set(aps.map((a) => a.mac.toUpperCase())), [aps]);

  const discoveryFloorLogs = useMemo(
    () => (aps.length === 0 ? [] : discoveryLogs.filter((l) => floorMacs.has(l.checkpoint_id.toUpperCase()))),
    [discoveryLogs, floorMacs, aps.length],
  );

  const distinctGuardIds = useMemo(
    () => Array.from(new Set(discoveryFloorLogs.map((l) => l.guard_id))).sort(),
    [discoveryFloorLogs],
  );

  // Default guard = guard of the most recent cycle on this floor, within the
  // discovery window. Only steers when unset/invalid — an explicit pick survives.
  useEffect(() => {
    if (guardId && distinctGuardIds.includes(guardId)) return;
    if (distinctGuardIds.length === 0) { setGuardId(null); return; }
    let best: { id: string; start: string } | null = null;
    for (const l of discoveryFloorLogs) {
      if (!best || l.expected_arrival > best.start) best = { id: l.guard_id, start: l.expected_arrival };
    }
    setGuardId(best?.id ?? distinctGuardIds[0]);
  }, [distinctGuardIds, discoveryFloorLogs, guardId]);

  // Once a guard is selected, fetch THEIR full log history (bounded, indexed
  // by guard_id) — not limited to the discovery window, so older cycles for
  // this specific guard are still reachable even if other guards' more recent
  // activity would otherwise have pushed them out of a global recent-N query.
  useEffect(() => {
    if (!guardId) { setGuardLogs([]); return; }
    return subscribeToPatrolLogsByGuard(guardId, GUARD_LOG_LIMIT, setGuardLogs);
  }, [guardId, refreshKey]);

  const guardFloorLogs = useMemo(
    () => (aps.length === 0 ? [] : guardLogs.filter((l) => floorMacs.has(l.checkpoint_id.toUpperCase()))),
    [guardLogs, floorMacs, aps.length],
  );

  const cycles: Cycle[] = useMemo(() => {
    const groups = new Map<string, Cycle>();
    for (const log of guardFloorLogs) {
      const key = cycleKeyOf(log);
      let g = groups.get(key);
      if (!g) { g = { key, start: log.expected_arrival, logs: [] }; groups.set(key, g); }
      if (log.expected_arrival < g.start) g.start = log.expected_arrival;
      g.logs.push(log);
    }
    return Array.from(groups.values()).sort((a, b) => (a.start < b.start ? 1 : -1)); // most recent first
  }, [guardFloorLogs]);

  useEffect(() => {
    if (cycleKey && cycles.some((c) => c.key === cycleKey)) return;
    setCycleKey(cycles[0]?.key ?? null);
  }, [cycles, cycleKey]);

  const selectedCycle = cycles.find((c) => c.key === cycleKey) ?? null;

  const apById = useMemo(() => new Map(aps.map((a) => [a.id, a])), [aps]);
  const routeAps = useMemo(
    () => (activeFloor?.patrol_route ?? []).map((id) => apById.get(id)).filter((a): a is APRecord => !!a),
    [activeFloor?.patrol_route, apById],
  );

  // Deterministic ordering (Prompt 121) before the mac-keyed map below —
  // relying on Firestore/JS's arbitrary tie-break on expected_arrival would
  // let this map's construction order (and thus which log wins on a
  // duplicate-mac collision) vary between loads.
  const sortedCycleLogs = useMemo(
    () => sortPatrolLogsDeterministically(selectedCycle?.logs ?? [], routeAps),
    [selectedCycle, routeAps],
  );

  const logByMac = useMemo(() => {
    const m = new Map<string, PatrolLogRecord>();
    for (const log of sortedCycleLogs) m.set(log.checkpoint_id.toUpperCase(), log);
    return m;
  }, [sortedCycleLogs]);

  const loggedCount = routeAps.filter((ap) => logByMac.has(ap.mac.toUpperCase())).length;

  const arrivalTimes = sortedCycleLogs
    .map((l) => l.actual_arrival)
    .filter((t): t is string => t !== null)
    .sort();
  const elapsedStart = arrivalTimes[0] ?? null;
  const elapsedEnd = arrivalTimes[arrivalTimes.length - 1] ?? null;

  function rowStatus(log: PatrolLogRecord | undefined): RowStatus {
    if (!log) return "No record";
    if (log.actual_arrival === null) return "Missed";
    return log.compliant ? "Compliant" : "Short dwell";
  }

  const STATUS_STYLE: Record<RowStatus, string> = {
    Compliant: "text-s-success",
    "Short dwell": "text-s-accent",
    Missed: "text-s-danger",
    "No record": "text-s-muted",
  };

  const noBuildings = buildings.length === 0;
  const noRoute = !!activeFloor && (!activeFloor.patrol_enabled || routeAps.length === 0);

  return (
    <div className="max-w-[1100px] mx-auto space-y-4">
      {/* Selectors + print button — hidden entirely when printed */}
      <div className="no-print flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase mr-2">Patrol Reports</h1>
        {buildings.length > 1 && (
          <SelectDropdown
            label="Building" items={buildings} selectedId={buildingId}
            getId={(b) => b.id} getLabel={(b) => b.name}
            onSelect={(id) => { setBuildingId(id); setFloorId(null); }}
          />
        )}
        {floors.length > 1 && (
          <SelectDropdown
            label="Floor" items={floors} selectedId={floorId}
            getId={(f) => f.id} getLabel={(f) => f.name}
            onSelect={setFloorId}
          />
        )}
        {distinctGuardIds.length > 0 && (
          <SelectDropdown
            label="Guard" items={distinctGuardIds.map((id) => ({ id }))} selectedId={guardId}
            getId={(g) => g.id} getLabel={(g) => g.id}
            onSelect={setGuardId}
          />
        )}
        {cycles.length > 0 && (
          <SelectDropdown
            label="Cycle" items={cycles} selectedId={cycleKey}
            getId={(c) => c.key} getLabel={(c) => fmtDate(c.start)}
            onSelect={setCycleKey}
            scrollable
          />
        )}
        {guardId && (
          <button
            onClick={() => setRefreshKey((k) => k + 1)}
            title="Refresh cycle list"
            aria-label="Refresh cycle list"
            className="h-7 w-7 flex items-center justify-center rounded-lg bg-s-elevated border border-s-border text-s-muted hover:border-s-accent hover:text-s-text transition-colors"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          </button>
        )}
        <button
          onClick={() => window.print()}
          disabled={!selectedCycle}
          className="ml-auto px-3 py-1.5 rounded-lg bg-s-accent text-s-base text-xs font-bold font-mono disabled:opacity-40 hover:opacity-90 transition-opacity"
        >
          Print / Save as PDF
        </button>
      </div>

      {noBuildings ? (
        <p className="text-s-muted text-sm font-mono">No buildings configured.</p>
      ) : noRoute ? (
        <p className="text-s-muted text-sm font-mono">This floor has no patrol route configured.</p>
      ) : !selectedCycle ? (
        <p className="text-s-muted text-sm font-mono">No patrol cycles recorded for this floor yet.</p>
      ) : (
        <div className="patrol-report-root bento-card space-y-4">
          {/* Header — factual only. No "complete", no completion percentage:
              there is no completion flag, and a finished round can legitimately
              be one log short (the never-written final-checkpoint case). */}
          <div className="space-y-1">
            <h2 className="font-mono text-sm font-bold text-s-text">
              Patrol Checkpoint Sequence — {guardId}
            </h2>
            <p className="font-mono text-xs text-s-muted">
              {activeFloor?.name} · cycle started {fmtDate(selectedCycle.start)}
              {elapsedStart && elapsedEnd && (
                <> · elapsed {fmtTime(elapsedStart)}–{fmtTime(elapsedEnd)}</>
              )}
              {" · "}{loggedCount} of {routeAps.length} checkpoints logged
            </p>
          </div>

          {/* Map — deterministic rendering from known checkpoint coordinates.
              This is "checkpoint sequence", not "path taken": no position
              history exists, only straight segments between checkpoints. */}
          <div className="patrol-report-map relative w-full rounded-xl overflow-hidden border border-s-border bg-s-elevated">
            {activeFloor?.url && (
              <img
                src={activeFloor.url}
                alt={activeFloor.name}
                className="w-full h-auto block"
                onLoad={(e) => {
                  const img = e.currentTarget;
                  setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
                }}
              />
            )}
            {naturalSize && activeFloor?.scale_pixels_per_meter && (
              <div className="absolute inset-0">
                <PatrolRouteOverlay
                  aps={aps}
                  route={activeFloor.patrol_route ?? []}
                  logs={selectedCycle.logs}
                  positions={[]}
                  naturalSize={naturalSize}
                  scale={activeFloor.scale_pixels_per_meter}
                  proximityRadiusM={activeFloor.patrol_proximity_radius_m ?? 1.0}
                  showDetails
                />
              </div>
            )}
            {!activeFloor?.scale_pixels_per_meter && (
              <div className="absolute bottom-0 inset-x-0 px-4 py-2.5 bg-s-elevated/95 border-t border-s-border">
                <p className="font-mono text-[10px] text-s-muted">
                  Floor plan not calibrated — checkpoint positions cannot be plotted.
                </p>
              </div>
            )}
          </div>

          {/* Checkpoint table — route order, "No record" kept distinct from
              "Missed": Missed means the tracker observed a skip; No record
              means nothing was ever written for that checkpoint this cycle. */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-left text-s-muted border-b border-s-border">
                  <th className="py-1.5 pr-3">#</th>
                  <th className="py-1.5 pr-3">Checkpoint</th>
                  <th className="py-1.5 pr-3">Timer from</th>
                  <th className="py-1.5 pr-3">Arrived</th>
                  <th className="py-1.5 pr-3">Dwell</th>
                  <th className="py-1.5 pr-3">Required</th>
                  <th className="py-1.5 pr-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {routeAps.map((ap, idx) => {
                  const log = logByMac.get(ap.mac.toUpperCase());
                  const status = rowStatus(log);
                  const shortfall = log && !log.compliant && log.actual_arrival !== null
                    ? Math.max(0, log.min_dwell_required - log.dwell_time_seconds)
                    : null;
                  return (
                    <tr key={ap.id} className="border-b border-s-border/50">
                      <td className="py-1.5 pr-3 text-s-muted">{idx + 1}</td>
                      <td className="py-1.5 pr-3 text-s-text">{ap.name}</td>
                      <td className="py-1.5 pr-3 text-s-muted">
                        {log && log.actual_arrival !== null ? fmtTime(log.expected_arrival) : "—"}
                      </td>
                      <td className="py-1.5 pr-3 text-s-muted">
                        {log ? (log.actual_arrival ? fmtTime(log.actual_arrival) : "Not reached") : "—"}
                      </td>
                      <td className="py-1.5 pr-3 text-s-muted">{log ? `${log.dwell_time_seconds}s` : "—"}</td>
                      <td className="py-1.5 pr-3 text-s-muted">{log ? `${log.min_dwell_required}s` : "—"}</td>
                      <td className={`py-1.5 pr-3 font-semibold ${STATUS_STYLE[status]}`}>
                        {status}
                        {shortfall !== null && shortfall > 0 && (
                          <span className="text-s-muted font-normal"> (short by {shortfall}s)</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
