"use client";
import { useEffect, useRef, useState } from "react";
import { subscribeToAPs, savePatrolConfig, type APRecord } from "@/services/floorService";
import type { FloorRecord } from "@/types/floor";
import { toast } from "@/store/toastStore";

interface Props {
  buildingId: string;
  floor: FloorRecord;
  onClose: () => void;
  onSaved: (patrolEnabled: boolean, patrolRoute: string[], patrolIntervalMinutes: number) => void;
}

const SETTLE_MS = 260;

export default function PatrolConfigPanel({
  buildingId,
  floor,
  onClose,
  onSaved,
}: Props) {
  const [aps, setAps] = useState<APRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [patrolEnabled, setPatrolEnabled] = useState(floor.patrol_enabled ?? false);
  const [routeIds, setRouteIds] = useState<string[]>(floor.patrol_route ?? []);
  const [intervalMinutes, setIntervalMinutes] = useState(floor.patrol_interval_minutes ?? 10);
  const [saving, setSaving] = useState(false);

  // Drag state — the row being dragged lifts and moves via CSS transform;
  // routeIds itself is only mutated once, after the settle animation
  // finishes. Reordering the real array on every pointermove (and letting
  // React re-render items into new DOM slots mid-drag) is what makes a drag
  // look like it jumps or grabs more than the one row.
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [dragDeltaY, setDragDeltaY] = useState(0);
  const [isSettling, setIsSettling] = useState(false);

  const routeInitialized = useRef(false);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const dragOriginIndexRef = useRef(0);
  const dragOverIndexRef = useRef(0);
  const dragStartYRef = useRef(0);
  const naturalTopsRef = useRef<number[]>([]);
  const naturalHeightsRef = useRef<number[]>([]);
  const gapPxRef = useRef(0);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    routeInitialized.current = false;
    const unsub = subscribeToAPs(buildingId, floor.id, (data) => {
      setAps(data);
      const liveIds = new Set(data.map((a) => a.id));
      if (!routeInitialized.current) {
        routeInitialized.current = true;
        if (!floor.patrol_route || floor.patrol_route.length === 0) {
          const sorted = [...data].sort((a, b) => a.name.localeCompare(b.name));
          setRouteIds(sorted.map((a) => a.id));
        } else {
          setRouteIds(floor.patrol_route.filter((id) => liveIds.has(id)));
        }
      } else {
        setRouteIds((prev) => prev.filter((id) => liveIds.has(id)));
      }
      setLoading(false);
    });
    return unsub;
  }, [buildingId, floor.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const apById = Object.fromEntries(aps.map((a) => [a.id, a]));
  const unrouted = aps.filter((a) => !routeIds.includes(a.id));

  const reorder = (from: number, to: number) => {
    if (from === to) return;
    setRouteIds((prev) => {
      const next = [...prev];
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
  };

  const measureLayout = () => {
    const tops: number[] = [];
    const heights: number[] = [];
    routeIds.forEach((id) => {
      const rect = rowRefs.current[id]?.getBoundingClientRect();
      tops.push(rect?.top ?? 0);
      heights.push(rect?.height ?? 0);
    });
    naturalTopsRef.current = tops;
    naturalHeightsRef.current = heights;
    gapPxRef.current = tops.length >= 2 ? tops[1] - tops[0] - heights[0] : 0;
  };

  // The list as it would lay out with the dragged row removed — every row
  // after it collapses upward by exactly the dragged row's own height+gap.
  // The live drag-over target and the final settle position are both
  // computed against this same reference frame, so they always agree.
  const collapsedLayout = (originIdx: number) => {
    const draggedH = (naturalHeightsRef.current[originIdx] ?? 0) + gapPxRef.current;
    const tops: number[] = [];
    const heights: number[] = [];
    naturalTopsRef.current.forEach((t, i) => {
      if (i === originIdx) return;
      tops.push(i > originIdx ? t - draggedH : t);
      heights.push(naturalHeightsRef.current[i]);
    });
    return { tops, heights };
  };

  const handleRowPointerDown = (id: string) => (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("button")) return;
    if (dragId !== null) return;
    e.preventDefault();
    if (settleTimerRef.current !== null) {
      clearTimeout(settleTimerRef.current);
      settleTimerRef.current = null;
    }
    const idx = routeIds.indexOf(id);
    measureLayout();
    dragOriginIndexRef.current = idx;
    dragOverIndexRef.current = idx;
    dragStartYRef.current = e.clientY;
    setDragId(id);
    setDragOverIndex(idx);
    setDragDeltaY(0);
    setIsSettling(false);
  };

  useEffect(() => {
    if (dragId === null) return;

    const handleMove = (e: PointerEvent) => {
      const delta = e.clientY - dragStartYRef.current;
      setDragDeltaY(delta);

      const origin = dragOriginIndexRef.current;
      const { tops, heights } = collapsedLayout(origin);
      const currentCenter =
        (naturalTopsRef.current[origin] ?? 0) + (naturalHeightsRef.current[origin] ?? 0) / 2 + delta;

      let target = 0;
      for (let i = 0; i < tops.length; i++) {
        if (tops[i] + heights[i] / 2 < currentCenter) target++;
      }
      target = Math.max(0, Math.min(routeIds.length - 1, target));
      if (target !== dragOverIndexRef.current) {
        dragOverIndexRef.current = target;
        setDragOverIndex(target);
      }
    };

    const handleUp = () => {
      const from = dragOriginIndexRef.current;
      const to = dragOverIndexRef.current;
      const { tops, heights } = collapsedLayout(from);
      const targetTop =
        tops.length === 0
          ? naturalTopsRef.current[from] ?? 0
          : to < tops.length
          ? tops[to]
          : tops[tops.length - 1] + heights[heights.length - 1] + gapPxRef.current;

      // Glide to the exact target slot first (array order untouched), then
      // commit the reorder once that transition finishes.
      setDragDeltaY(targetTop - (naturalTopsRef.current[from] ?? 0));
      setIsSettling(true);

      settleTimerRef.current = setTimeout(() => {
        reorder(from, to);
        setDragId(null);
        setDragOverIndex(null);
        setDragDeltaY(0);
        setIsSettling(false);
        settleTimerRef.current = null;
      }, SETTLE_MS);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    window.addEventListener("pointercancel", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      window.removeEventListener("pointercancel", handleUp);
    };
  }, [dragId]); // eslint-disable-line react-hooks/exhaustive-deps

  const removeFromRoute = (id: string) => {
    setRouteIds((prev) => prev.filter((r) => r !== id));
  };

  const addToRoute = (id: string) => {
    setRouteIds((prev) => [...prev, id]);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await savePatrolConfig(buildingId, floor.id, patrolEnabled, routeIds, intervalMinutes);
      onSaved(patrolEnabled, routeIds, intervalMinutes);
      toast.success("Patrol configuration saved");
    } catch {
      toast.error("Failed to save patrol config");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
          Patrol Configuration
        </p>
        <button
          onClick={onClose}
          className="text-s-muted hover:text-s-text transition-colors"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Patrol enabled toggle */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-s-elevated border border-s-border">
        <div>
          <p className="text-sm font-medium text-s-text">Patrol Active</p>
          <p className="text-xs text-s-muted mt-0.5">
            Enable patrol tracking and auto-report generation for this floor
          </p>
        </div>
        <div
          role="button"
          tabIndex={0}
          onClick={() => setPatrolEnabled((v) => !v)}
          onKeyDown={(e) => e.key === "Enter" && setPatrolEnabled((v) => !v)}
          className="cursor-pointer shrink-0"
        >
          <div
            className={`relative w-10 h-5 rounded-full transition-colors ${
              patrolEnabled ? "bg-s-success" : "bg-s-border"
            }`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                patrolEnabled ? "translate-x-[22px]" : "translate-x-0.5"
              }`}
            />
          </div>
        </div>
      </div>

      {/* Cycle window — per-floor, not a global (Prompt 122). Rolling from the
          guard's first detection, not a wall-clock grid; "suit the size of
          the space" means this has to be settable here, not just defaulted. */}
      {patrolEnabled && (
        <div className="flex items-center justify-between p-3 rounded-lg bg-s-elevated border border-s-border">
          <div>
            <p className="text-sm font-medium text-s-text">Cycle Window</p>
            <p className="text-xs text-s-muted mt-0.5">
              Minutes per patrol cycle. A checkpoint not reached before the window
              closes shows as not-yet-reached, not missed.
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <input
              type="number"
              min={1}
              value={intervalMinutes}
              onChange={(e) => setIntervalMinutes(Math.max(1, Number(e.target.value) || 1))}
              className="w-14 px-2 py-1 rounded-lg bg-s-base border border-s-border text-xs text-s-text font-mono text-center"
            />
            <span className="text-xs text-s-muted font-mono">min</span>
          </div>
        </div>
      )}

      {/* Route order — only shown when patrol enabled */}
      {patrolEnabled && (
        <div className="space-y-2">
          <p className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
            Route Order
          </p>
          <p className="text-xs text-s-muted">
            Guards must visit APs in this sequence. Grab a row and drag it up or down to reorder.
          </p>

          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 bg-s-elevated rounded-lg animate-pulse" />
              ))}
            </div>
          ) : routeIds.length === 0 ? (
            <p className="text-xs text-s-muted font-mono py-3 text-center">
              No APs in route — add APs to the floor first
            </p>
          ) : (
            <div className="space-y-1.5" style={{ userSelect: dragId !== null ? "none" : undefined }}>
              {routeIds.map((id, idx) => {
                const ap = apById[id];
                if (!ap) return null;

                const isDragged = dragId === id;
                const isLifted = isDragged && !isSettling;

                let shift = 0;
                if (dragId !== null && !isDragged && dragOverIndex !== null) {
                  const from = dragOriginIndexRef.current;
                  const to = dragOverIndex;
                  if (to > from && idx > from && idx <= to) shift = -1;
                  else if (to < from && idx >= to && idx < from) shift = 1;
                }
                const draggedFootprint =
                  dragId !== null
                    ? (naturalHeightsRef.current[dragOriginIndexRef.current] ?? 0) + gapPxRef.current
                    : 0;
                const translateY = isDragged ? dragDeltaY : shift * draggedFootprint;

                return (
                  <div
                    key={id}
                    ref={(el) => { rowRefs.current[id] = el; }}
                    onPointerDown={handleRowPointerDown(id)}
                    className={`relative flex items-center gap-2 px-3 py-2 rounded-lg bg-s-elevated border touch-none ${
                      isDragged ? "cursor-grabbing border-s-accent" : "cursor-grab border-s-border"
                    }`}
                    style={{
                      transform: `translateY(${translateY}px) scale(${isLifted ? 1.015 : 1})`,
                      boxShadow: isLifted
                        ? "0 18px 36px -8px rgba(0,0,0,.45), 0 6px 14px -4px rgba(0,0,0,.35)"
                        : "0 0 0 0 rgba(0,0,0,0)",
                      // Only animate while a drag (including its settle glide) is
                      // actually in progress. The instant dragId resets to null —
                      // the same frame the reorder commits and this row's transform
                      // snaps back to 0 as it lands in its real DOM slot — a
                      // lingering transition would animate that snap-back instead
                      // of letting it land instantly, which is what reads as a
                      // flick/jump.
                      transition:
                        dragId !== null && !isLifted
                          ? "transform 260ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 260ms ease, border-color 200ms ease"
                          : "none",
                      zIndex: isDragged ? 20 : 1,
                    }}
                  >
                    <span className="text-s-muted shrink-0" title="Drag to reorder">
                      <svg width="10" height="14" viewBox="0 0 10 14" fill="currentColor">
                        <circle cx="2" cy="2" r="1.3" /><circle cx="8" cy="2" r="1.3" />
                        <circle cx="2" cy="7" r="1.3" /><circle cx="8" cy="7" r="1.3" />
                        <circle cx="2" cy="12" r="1.3" /><circle cx="8" cy="12" r="1.3" />
                      </svg>
                    </span>
                    <span className="font-mono text-[10px] text-s-accent w-5 shrink-0 text-center">
                      {idx + 1}
                    </span>
                    <span className="flex-1 text-xs text-s-text font-medium truncate">
                      {ap.name}
                    </span>
                    <span className="font-mono text-[9px] text-s-muted truncate max-w-[100px]">
                      {ap.mac}
                    </span>
                    <button
                      onClick={() => removeFromRoute(id)}
                      className="p-1 rounded text-s-muted hover:text-s-danger transition-colors shrink-0"
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {unrouted.length > 0 && (
            <div className="space-y-1">
              <p className="font-mono text-[9px] text-s-muted tracking-widest uppercase mt-3">
                Not in Route
              </p>
              {unrouted.map((ap) => (
                <div
                  key={ap.id}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-s-border"
                >
                  <span className="flex-1 text-xs text-s-muted truncate">{ap.name}</span>
                  <button
                    onClick={() => addToRoute(ap.id)}
                    className="text-xs text-s-accent hover:opacity-80 transition-opacity font-mono"
                  >
                    + Add
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Save */}
      <button
        onClick={handleSave}
        disabled={saving}
        className="w-full py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5"
      >
        {saving && (
          <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />
        )}
        {saving ? "Saving…" : "Save Patrol Config"}
      </button>
    </div>
  );
}
