"use client";
import { useEffect, useState } from "react";
import { listAPs, savePatrolConfig, type APRecord } from "@/services/floorService";
import type { FloorRecord } from "@/types/floor";
import { toast } from "@/store/toastStore";

interface Props {
  buildingId: string;
  floor: FloorRecord;
  onClose: () => void;
  onSaved: (patrolEnabled: boolean, patrolRoute: string[]) => void;
}

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
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listAPs(buildingId, floor.id)
      .then((data) => {
        setAps(data);
        const liveIds = new Set(data.map((a) => a.id));
        if (!floor.patrol_route || floor.patrol_route.length === 0) {
          const sorted = [...data].sort((a, b) => a.name.localeCompare(b.name));
          setRouteIds(sorted.map((a) => a.id));
        } else {
          setRouteIds(floor.patrol_route.filter((id) => liveIds.has(id)));
        }
      })
      .catch(() => toast.error("Failed to load APs"))
      .finally(() => setLoading(false));
  }, [buildingId, floor.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const apById = Object.fromEntries(aps.map((a) => [a.id, a]));
  const unrouted = aps.filter((a) => !routeIds.includes(a.id));

  const moveUp = (idx: number) => {
    if (idx === 0) return;
    const next = [...routeIds];
    [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
    setRouteIds(next);
  };

  const moveDown = (idx: number) => {
    if (idx === routeIds.length - 1) return;
    const next = [...routeIds];
    [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
    setRouteIds(next);
  };

  const removeFromRoute = (id: string) => {
    setRouteIds((prev) => prev.filter((r) => r !== id));
  };

  const addToRoute = (id: string) => {
    setRouteIds((prev) => [...prev, id]);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await savePatrolConfig(buildingId, floor.id, patrolEnabled, routeIds);
      onSaved(patrolEnabled, routeIds);
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

      {/* Route order — only shown when patrol enabled */}
      {patrolEnabled && (
        <div className="space-y-2">
          <p className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
            Route Order
          </p>
          <p className="text-xs text-s-muted">
            Guards must visit APs in this sequence. Use arrows to reorder.
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
            <div className="space-y-1.5">
              {routeIds.map((id, idx) => {
                const ap = apById[id];
                if (!ap) return null;
                return (
                  <div
                    key={id}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg bg-s-elevated border border-s-border"
                  >
                    <span className="font-mono text-[10px] text-s-accent w-5 shrink-0 text-center">
                      {idx + 1}
                    </span>
                    <span className="flex-1 text-xs text-s-text font-medium truncate">
                      {ap.name}
                    </span>
                    <span className="font-mono text-[9px] text-s-muted truncate max-w-[100px]">
                      {ap.mac}
                    </span>
                    <div className="flex gap-0.5 shrink-0">
                      <button
                        onClick={() => moveUp(idx)}
                        disabled={idx === 0}
                        className="p-1 rounded text-s-muted hover:text-s-text disabled:opacity-25 transition-colors"
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="18 15 12 9 6 15" />
                        </svg>
                      </button>
                      <button
                        onClick={() => moveDown(idx)}
                        disabled={idx === routeIds.length - 1}
                        className="p-1 rounded text-s-muted hover:text-s-text disabled:opacity-25 transition-colors"
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="6 9 12 15 18 9" />
                        </svg>
                      </button>
                    </div>
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
