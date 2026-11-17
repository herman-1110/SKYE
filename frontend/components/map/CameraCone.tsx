"use client";
import { useEffect, useRef, useState, type RefObject } from "react";
import {
  DEFAULT_FOV_DEG, conePath, facingBetween, facingLabel, facingVector, parseFacing, parseFov, roundFacing,
} from "@/utils/cameraFacing";

// Which way a camera faces (Prompt 143, D2): a translucent cone under its
// marker, on the dashboard map and in Manage Devices. It shows a direction,
// not coverage, so its length is fixed on screen at about three markers
// whatever the image's size (D2.4). In Manage Devices only, a camera with no
// facing saved gets a faint, dashed default cone that can be turned the same
// way (Herman, 18 Nov). The maths is in utils/cameraFacing.ts.

/** The cone's length on screen: about three 26 px camera markers. */
export const CONE_LENGTH_PX = 78;
const HANDLE_R = 7;
const PAD = HANDLE_R + 3;   // room in the box for the handle at the tip

/** The cone for one camera at (xPct, yPct), fractions of the image. With
 *  onHandlePointerDown it has a rotate handle at its tip (Manage Devices).
 *  notSet draws it faint and dashed: the default cone Manage Devices shows
 *  for a camera with no saved facing (Herman, 18 Nov). */
export default function CameraCone({ xPct, yPct, facingDeg, fovDeg, color, notSet = false, onHandlePointerDown }: {
  xPct: number;
  yPct: number;
  facingDeg: number;
  fovDeg?: number | null;
  color: string;
  notSet?: boolean;
  onHandlePointerDown?: (e: React.PointerEvent<SVGCircleElement>) => void;
}) {
  const r = CONE_LENGTH_PX;
  const c = r + PAD;
  const size = 2 * c;
  const tip = facingVector(facingDeg);
  return (
    // No z-index: drawn in page order, under the markers (z-index 10) and the workers drawn after it
    <div
      className="absolute"
      style={{ left: `${xPct * 100}%`, top: `${yPct * 100}%`, width: size, height: size, transform: "translate(-50%, -50%)", pointerEvents: "none" }}
    >
      {/* A box of fixed pixels around the camera: the image's own pixels scale evenly with it, so the angle drawn is the angle stored */}
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: "block", overflow: "visible" }} aria-hidden="true">
        <path d={conePath(c, c, r, facingDeg, fovDeg ?? DEFAULT_FOV_DEG)} fill={color} fillOpacity={notSet ? 0.05 : 0.16}
          stroke={color} strokeOpacity={0.6} strokeWidth={1.5} strokeDasharray={notSet ? "4 3" : undefined} strokeLinejoin="round" />
        {onHandlePointerDown && (
          <circle cx={c + tip.x * r} cy={c + tip.y * r} r={HANDLE_R} fill="var(--bg-surface)" stroke={color} strokeWidth={2}
            style={{ pointerEvents: "auto", cursor: "grab", touchAction: "none" }} onPointerDown={onHandlePointerDown}>
            <title>Drag to turn the camera</title>
          </circle>
        )}
      </svg>
    </div>
  );
}

/** The camera dialog's Facing and Field of view boxes (D2.3). Facing shows
 *  its compass word ("135° (SE)"); the field of view waits for a facing. */
export function CameraDirectionFields({ facing, fov, error, onFacing, onFov }: {
  facing: string;
  fov: string;
  error: string;
  onFacing: (text: string) => void;
  onFov: (text: string) => void;
}) {
  const f = parseFacing(facing);
  const input = "w-full bg-s-elevated border rounded-lg px-3 py-2 text-sm font-mono text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors disabled:opacity-40";
  const label = "font-mono text-[10px] text-s-muted tracking-widest uppercase";
  return (
    <div className="space-y-1">
      <div className="flex gap-2">
        <div className="flex-1 min-w-0 space-y-1">
          <label className={label}>Facing (°)</label>
          <input type="text" inputMode="decimal" placeholder="Not set" value={facing} aria-label="Facing, in degrees clockwise from up"
            onChange={(e) => onFacing(e.target.value)} className={input}
            style={{ borderColor: f.ok ? "var(--border)" : "var(--danger, #ef4444)" }} />
          <p className="font-mono text-[10px] text-s-muted min-h-[14px]">{f.ok && f.value !== null ? facingLabel(f.value) : ""}</p>
        </div>
        <div className="flex-1 min-w-0 space-y-1">
          <label className={label}>Field of view (°)</label>
          <input type="text" inputMode="decimal" placeholder={String(DEFAULT_FOV_DEG)} value={fov} disabled={!facing.trim()}
            aria-label="Field of view, in degrees" onChange={(e) => onFov(e.target.value)} className={input}
            style={{ borderColor: parseFov(fov).ok ? "var(--border)" : "var(--danger, #ef4444)" }} />
        </div>
      </div>
      {error && <p style={{ color: "var(--danger, #ef4444)", fontSize: 11 }}>{error}</p>}
      <p className="font-mono text-[10px] text-s-muted">
        Clockwise from the top of the plan: 0 up, 90 right, 180 down. Leave Facing empty for no direction.
      </p>
    </div>
  );
}

/** Turning a camera with the handle at its cone's tip (D2.3). The angle is
 *  worked out from the camera to the cursor in the image's pixels as drawn
 *  (imgRef), in whole degrees. Releasing saves it with save(); until that
 *  resolves the new angle stays drawn, so the cone doesn't jump back. Esc,
 *  or a cancelled pointer, puts it back and saves nothing. On a saved cone a
 *  release without a turn saves nothing; on a default one (unset: the camera
 *  has no facing saved, Herman, 18 Nov) the first release saves the angle
 *  shown, even the default itself. shownFacing(id) is the angle to draw while
 *  a turn is under way, else null. */
export function useConeRotation(imgRef: RefObject<HTMLImageElement | null>, save: (id: string, facingDeg: number) => Promise<void>) {
  const [shown, setShown] = useState<{ id: string; deg: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const drag = useRef<{ id: string; cam: { x: number; y: number }; start: number; deg: number; unset: boolean } | null>(null);
  const saveRef = useRef(save);
  saveRef.current = save;

  const begin = (e: React.PointerEvent, id: string, cam: { x: number; y: number }, facingDeg: number, unset = false) => {
    e.preventDefault();
    e.stopPropagation();
    drag.current = { id, cam, start: facingDeg, deg: facingDeg, unset };
    setShown({ id, deg: facingDeg });
    setDragging(true);
  };

  useEffect(() => {
    if (!dragging) return;
    const move = (e: PointerEvent) => {
      const d = drag.current, img = imgRef.current;
      if (!d || !img) return;
      const box = img.getBoundingClientRect();
      if (!box.width || !box.height) return;
      const cursor = { x: (e.clientX - box.left) / box.width, y: (e.clientY - box.top) / box.height };
      d.deg = roundFacing(facingBetween(d.cam, cursor, { w: box.width, h: box.height }));
      setShown({ id: d.id, deg: d.deg });
    };
    const putBack = () => {
      drag.current = null;
      setDragging(false);
      setShown(null);
    };
    const release = () => {
      const d = drag.current;
      drag.current = null;
      setDragging(false);
      if (!d || (!d.unset && d.deg === d.start)) { setShown(null); return; }
      saveRef.current(d.id, d.deg).finally(() => setShown(null));
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") putBack(); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", putBack);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", release);
      window.removeEventListener("pointercancel", putBack);
      window.removeEventListener("keydown", key);
    };
  }, [dragging, imgRef]);

  const shownFacing = (id: string): number | null => (shown && shown.id === id ? shown.deg : null);
  return { begin, shownFacing, turning: dragging };
}
