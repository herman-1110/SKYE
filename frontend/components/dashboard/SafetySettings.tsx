"use client";
import { useEffect, useState } from "react";
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
  const [manDownMinutes, setManDownMinutes] = useState<number>(5);
  const [collisionDistance, setCollisionDistance] = useState<number>(2.0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  useEffect(() => {
    getSafetySettings()
      .then((s) => {
        setInitial(s);
        setManDownMinutes(s.man_down_minutes);
        setCollisionDistance(s.collision_distance_m);
        setLastUpdated(s.updated_at ?? null);
      })
      .catch(() => toast.error("Failed to load safety settings"))
      .finally(() => setLoading(false));
  }, []);

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
  const canSave = !loading && !saving && !manDownInvalid && !collisionInvalid && !unchanged;

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

      {loading ? (
        <p className="font-mono text-[10px] text-s-muted text-center py-4 tracking-widest">
          Loading settings…
        </p>
      ) : (
        <div className="bento-card p-5 space-y-5">
          <div className="space-y-2">
            <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
              Man-down stillness timer (minutes) <span className="text-s-danger">*</span>
            </label>
            <input
              type="number"
              min={MIN_MAN_DOWN}
              max={MAX_MAN_DOWN}
              step={1}
              value={Number.isFinite(manDownMinutes) ? manDownMinutes : ""}
              onChange={(e) => setManDownMinutes(parseInt(e.target.value, 10))}
              className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm font-mono text-s-text focus:outline-none focus:border-s-accent transition-colors"
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
              value={Number.isFinite(collisionDistance) ? collisionDistance : ""}
              onChange={(e) => setCollisionDistance(parseFloat(e.target.value))}
              className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm font-mono text-s-text focus:outline-none focus:border-s-accent transition-colors"
            />
            <p className="font-mono text-[10px] text-s-muted leading-relaxed">
              Worker–forklift predicted distance that triggers a collision alert.
              Range {MIN_COLLISION}–{MAX_COLLISION} m.
            </p>
          </div>

          {(manDownInvalid || collisionInvalid) && (
            <p className="font-mono text-[10px] text-s-danger leading-relaxed">
              {manDownInvalid && (
                <>Man-down timer must be a whole number from {MIN_MAN_DOWN} to {MAX_MAN_DOWN}.{" "}</>
              )}
              {collisionInvalid && (
                <>Collision distance must be between {MIN_COLLISION} and {MAX_COLLISION} m.</>
              )}
            </p>
          )}

          {lastUpdated && (
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
