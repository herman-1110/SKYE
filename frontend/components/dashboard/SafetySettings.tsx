"use client";
import { useCallback, useEffect, useState } from "react";
import {
  getSafetySettings,
  updateSafetySettings,
  type SafetySettings,
} from "@/services/safetySettingsService";
import { toast } from "@/store/toastStore";

const MIN_MAN_DOWN = 1;
const MAX_MAN_DOWN = 60;
const MIN_COLLISION = 0.5;
const MAX_COLLISION = 10;

export default function SafetySettings() {
  const [initial, setInitial] = useState<SafetySettings | null>(null);
  // No numbers until the live values have loaded (Prompt 143, D5): NaN shows
  // as an empty box. The page used to start at 5 and 2.0 and keep them when
  // the load failed, with Save on, so a click could overwrite the real values.
  const [manDownMinutes, setManDownMinutes] = useState<number>(NaN);
  const [collisionDistance, setCollisionDistance] = useState<number>(NaN);
  const [loadState, setLoadState] = useState<"loading" | "loaded" | "failed">("loading");
  const [saving, setSaving] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  // Only two numbers count as loaded; a failed request or anything else
  // leaves the form empty with Save off, and offers Retry.
  const load = useCallback(() => {
    setLoadState("loading");
    getSafetySettings()
      .then((s) => {
        if (!Number.isFinite(s?.man_down_minutes) || !Number.isFinite(s?.collision_distance_m)) {
          throw new Error("The settings came back without both values");
        }
        setInitial(s);
        setManDownMinutes(s.man_down_minutes);
        setCollisionDistance(s.collision_distance_m);
        setLastUpdated(s.updated_at ?? null);
        setLoadState("loaded");
      })
      .catch(() => setLoadState("failed"));
  }, []);

  useEffect(() => { load(); }, [load]);

  const loaded = loadState === "loaded" && initial !== null;

  const manDownInvalid =
    !Number.isInteger(manDownMinutes) ||
    manDownMinutes < MIN_MAN_DOWN ||
    manDownMinutes > MAX_MAN_DOWN;
  const collisionInvalid =
    !Number.isFinite(collisionDistance) ||
    collisionDistance < MIN_COLLISION ||
    collisionDistance > MAX_COLLISION;
  const unchanged =
    initial !== null &&
    initial.man_down_minutes === manDownMinutes &&
    initial.collision_distance_m === collisionDistance;
  // Save needs the real values loaded and one of them changed (D5.4).
  const canSave = loaded && !saving && !manDownInvalid && !collisionInvalid && !unchanged;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      const updated = await updateSafetySettings({
        man_down_minutes: manDownMinutes,
        collision_distance_m: collisionDistance,
      });
      setInitial(updated);
      setManDownMinutes(updated.man_down_minutes);
      setCollisionDistance(updated.collision_distance_m);
      setLastUpdated(updated.updated_at ?? null);
      toast.success("Safety settings updated");
    } catch (err: unknown) {
      const status = (err as { status?: number }).status;
      if (status === 403) {
        toast.error("Admin access required.");
      } else {
        toast.error("Failed to update safety settings");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase mr-1">
          Safety Thresholds
        </span>
      </div>

      {loadState === "loading" ? (
        <p className="font-mono text-[10px] text-s-muted text-center py-4 tracking-widest">
          Loading settings…
        </p>
      ) : (
        <div className="bento-card p-5 space-y-5">
          {loadState === "failed" && (
            <div className="flex items-center gap-3 rounded-lg px-3 py-2.5" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)" }}>
              <p className="flex-1 text-xs" style={{ color: "var(--danger, #ef4444)" }}>
                Couldn&apos;t load the current settings. Nothing can be saved until they load.
              </p>
              <button onClick={load} className="shrink-0 px-3 py-1.5 rounded-lg border border-s-border text-xs font-mono text-s-text hover:border-s-accent transition-colors">
                Retry
              </button>
            </div>
          )}

          <div className="space-y-2">
            <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
              Man-down stillness timer (minutes) <span className="text-s-danger">*</span>
            </label>
            <input
              type="number"
              min={MIN_MAN_DOWN}
              max={MAX_MAN_DOWN}
              step={1}
              value={loaded && Number.isFinite(manDownMinutes) ? manDownMinutes : ""}
              onChange={(e) => setManDownMinutes(parseInt(e.target.value, 10))}
              disabled={!loaded}
              className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm font-mono text-s-text focus:outline-none focus:border-s-accent transition-colors disabled:opacity-40"
            />
            <p className="font-mono text-[10px] text-s-muted leading-relaxed">
              How long a worker or guard must remain stationary before a man-down alert fires.
              Range {MIN_MAN_DOWN}–{MAX_MAN_DOWN} minutes.
            </p>
          </div>

          <div className="space-y-2">
            <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
              Collision proximity buffer (metres) <span className="text-s-danger">*</span>
            </label>
            <input
              type="number"
              min={MIN_COLLISION}
              max={MAX_COLLISION}
              step={0.1}
              value={loaded && Number.isFinite(collisionDistance) ? collisionDistance : ""}
              onChange={(e) => setCollisionDistance(parseFloat(e.target.value))}
              disabled={!loaded}
              className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm font-mono text-s-text focus:outline-none focus:border-s-accent transition-colors disabled:opacity-40"
            />
            <p className="font-mono text-[10px] text-s-muted leading-relaxed">
              Worker–forklift predicted distance that triggers a collision alert.
              Range {MIN_COLLISION}–{MAX_COLLISION} m.
            </p>
          </div>

          {loaded && (manDownInvalid || collisionInvalid) && (
            <p className="font-mono text-[10px] text-s-danger leading-relaxed">
              {manDownInvalid && (
                <>Man-down timer must be a whole number from {MIN_MAN_DOWN} to {MAX_MAN_DOWN}.{" "}</>
              )}
              {collisionInvalid && (
                <>Collision distance must be between {MIN_COLLISION} and {MAX_COLLISION} m.</>
              )}
            </p>
          )}

          {loaded && lastUpdated && (
            <p className="font-mono text-[10px] text-s-muted leading-relaxed">
              Last changed: {new Date(lastUpdated).toLocaleString()}
            </p>
          )}

          <div className="flex justify-end pt-1">
            <button
              onClick={handleSave}
              disabled={!canSave}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity"
            >
              {saving && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
              {saving ? "Saving…" : "Save Changes"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
