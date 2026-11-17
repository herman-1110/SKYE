"use client";
import { useCallback, useEffect, useState } from "react";
import {
  canPairWalls, formatMetres, guideGeometry, nearestWall, parseMetres, parseWallGuides, serialiseWallGuides,
  signedArea2, snapCorner, wallEnds, wallGuidesKey, wallLengthM,
  type Distances, type Frac, type ImageSize, type WallGuides,
} from "@/utils/wallGuides";
import { PolygonDraftHint, PolygonDraftPreview, usePolygonDraft } from "./PolygonDraft";

// Placement guides for Manage Devices (Prompt 143, D1, as changed on 18 Nov):
// the room's outline Herman draws, the two walls he picks on it, and two
// dimension lines from them to the device being placed, dragged or hovered.
// Every wall carries its length in metres. The maths is in utils/wallGuides.ts;
// the outline is drawn with the zone editor's drawing (PolygonDraft.tsx).
// Everything is drawn in percentages of the image, so the overlay needs no
// measuring; only line widths, text and label offsets are in pixels.

const ACCENT = "var(--accent)";
const MUTED = "var(--text-secondary)";
const HALO = "var(--bg-surface)";
const DANGER = "var(--danger, #ef4444)";
const SMALL_FONT = 10;
const pct = (v: number) => `${v * 100}%`;

/** What metres are counted in: the image's pixel size and the floor's px/m. */
export interface GuideScale { size: ImageSize; pxPerM: number }

export type WallStep = 1 | 2 | 3;

export const WALL_STEP_HINT: Record<WallStep, string> = {
  1: "Walls, step 1 of 3: click the room's corners, then right-click to close the outline. Hold Shift for a level or upright wall.",
  2: "Step 2 of 3: click the wall to measure X from. Esc cancels.",
  3: "Step 3 of 3: click another wall to measure Y from. Esc cancels.",
};

/** Step 3's hint when the wall under the cursor, or clicked, can't be the Y wall. */
export const PARALLEL_HINT = "That wall is within 30° of parallel to the X wall. Pick one that isn't. Esc cancels.";

/** The walls kept for this floor in this browser (D1.7), with a save and a
 *  clear. Every storage access is wrapped, like skye-theme in app/layout.tsx:
 *  where storage is blocked the walls still work, they just aren't kept. A
 *  rectangle saved before 18 Nov reads as no walls. */
export function useStoredWallGuides(floorId: string): [WallGuides | null, (g: WallGuides) => void, () => void] {
  const [walls, setWalls] = useState<WallGuides | null>(null);

  useEffect(() => {
    let raw: string | null = null;
    try { raw = window.localStorage.getItem(wallGuidesKey(floorId)); } catch { raw = null; }
    setWalls(parseWallGuides(raw));
  }, [floorId]);

  const save = useCallback((g: WallGuides) => {
    setWalls(g);
    try { window.localStorage.setItem(wallGuidesKey(floorId), serialiseWallGuides(g)); } catch { /* not kept */ }
  }, [floorId]);

  const clear = useCallback(() => {
    setWalls(null);
    try { window.localStorage.removeItem(wallGuidesKey(floorId)); } catch { /* nothing kept */ }
  }, [floorId]);

  return [walls, save, clear];
}

/** The three steps (D1.2, as changed on 18 Nov). Step 1 draws the outline the
 *  way a zone is drawn: a click adds a corner, a right-click closes it once it
 *  has 3, Esc clears the corners drawn so far; Shift makes the wall being drawn
 *  level or upright. Step 2 picks the X wall and step 3 the Y wall, the wall
 *  nearest the cursor each time; a Y wall within 30° of parallel to the X wall
 *  is refused. Esc in steps 2 and 3 cancels and keeps the walls there were. The
 *  editor passes its map's pointer events in, as fractions of the image. */
export function useWallSetup(onDone: (g: WallGuides) => void, size: ImageSize | null) {
  const [step, setStep] = useState<WallStep | null>(null);
  const draft = usePolygonDraft<Frac>();
  const [raw, setRaw] = useState<Frac | null>(null);          // the cursor in step 1, before Shift
  const [shift, setShift] = useState(false);
  const [tol, setTol] = useState<Frac>({ x: 0, y: 0 });      // 8 screen pixels in fractions: lining up with the first corner
  const [outline, setOutline] = useState<Frac[] | null>(null);
  const [xWall, setXWall] = useState<number | null>(null);
  const [hover, setHover] = useState<Frac | null>(null);
  const [refused, setRefused] = useState(false);
  const clearDraft = draft.clear;

  const reset = useCallback(() => {
    setStep(null); clearDraft(); setRaw(null); setShift(false);
    setOutline(null); setXWall(null); setHover(null); setRefused(false);
  }, [clearDraft]);

  useEffect(() => {
    if (step !== 2 && step !== 3) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") reset(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, reset]);

  // Shift pressed or let go without moving the mouse re-snaps the wall being drawn.
  useEffect(() => {
    if (step !== 1) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Shift") setShift(e.type === "keydown"); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onKey);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("keyup", onKey); };
  }, [step]);

  const snap = (p: Frac, withShift: boolean): Frac => {
    const pts = draft.points;
    if (!withShift || !size || pts.length === 0) return p;
    return snapCorner(pts[pts.length - 1], p, size, pts.length >= 2 ? pts[0] : null, tol);
  };

  const start = () => { reset(); setStep(1); };

  /** The cursor over the map; t is 8 screen pixels in fractions of the image. */
  const pointerMove = (p: Frac, withShift: boolean, t: Frac) => {
    setHover(p);
    if (step === 1) { setRaw(p); setShift(withShift); setTol(t); }
    if (step === 3) setRefused(false);
  };

  const click = (p: Frac, withShift: boolean) => {
    if (step === 1) { draft.add(snap(p, withShift)); return; }
    if (!outline || !size) return;
    const wall = nearestWall(outline, p, size);
    if (wall === null) return;
    if (step === 2) { setXWall(wall); setStep(3); return; }
    if (step === 3 && xWall !== null) {
      if (!canPairWalls(outline, xWall, wall, size)) { setRefused(true); return; }
      onDone({ corners: outline, xWall, yWall: wall });
      reset();
    }
  };

  /** The right-click in step 1: closes the outline once it has 3 corners. */
  const closeOutline = () => {
    if (step !== 1) return;
    const pts = draft.close();
    if (!pts) return;
    setOutline(pts); setRaw(null); setStep(2);
  };

  const cursor = step === 1 && raw ? snap(raw, shift) : null;
  const candidate = (step === 2 || step === 3) && outline && hover && size ? nearestWall(outline, hover, size) : null;
  const candidateRefused = step === 3 && outline !== null && size !== null && xWall !== null && candidate !== null
    && !canPairWalls(outline, xWall, candidate, size);

  return {
    step, corners: draft.points, cursor, outline, xWall, candidate, candidateRefused, refused,
    start, cancel: reset, pointerMove, click, closeOutline,
  };
}

/** A label over the plan; `small` ones are muted, like the walls' lengths. */
function Label({ x, y, dx = 0, dy = 0, anchor = "middle", small = false, children }: {
  x: number; y: number; dx?: number; dy?: number; anchor?: "start" | "middle" | "end"; small?: boolean; children: React.ReactNode;
}) {
  return (
    <text x={pct(x)} y={pct(y)} dx={dx} dy={dy} textAnchor={anchor} dominantBaseline="middle"
      fill={small ? MUTED : ACCENT} stroke={HALO} strokeWidth={3} paintOrder="stroke"
      style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: small ? SMALL_FONT : 11 }}>
      {children}
    </text>
  );
}

function Line({ a, b, color, width, dash, opacity = 1 }: {
  a: Frac; b: Frac; color: string; width: number; dash?: string; opacity?: number;
}) {
  return (
    <line x1={pct(a.x)} y1={pct(a.y)} x2={pct(b.x)} y2={pct(b.y)}
      stroke={color} strokeWidth={width} strokeDasharray={dash} strokeLinecap="round" opacity={opacity} />
  );
}

/** A unit normal to the segment a→b in pixels: towards `inward` (±1, the
 *  room's side by the outline's turning) when given, else above a mostly level
 *  segment or right of a mostly upright one. */
function normalOf(a: Frac, b: Frac, size: ImageSize, inward: 1 | -1 | null): { x: number; y: number } {
  const dx = (b.x - a.x) * size.w, dy = (b.y - a.y) * size.h;
  const len = Math.hypot(dx, dy) || 1;
  const n = { x: -dy / len, y: dx / len };
  if (inward !== null) return { x: n.x * inward, y: n.y * inward };
  const flip = Math.abs(dx) >= Math.abs(dy) ? n.y > 0 : n.x < 0;
  return flip ? { x: -n.x, y: -n.y } : n;
}

/** Text by the middle of a segment, set off along a normal: 6 px across and
 *  10 px up or down, as the rectangle's labels were. */
function SideText({ a, b, n, small = false, children }: {
  a: Frac; b: Frac; n: { x: number; y: number }; small?: boolean; children: React.ReactNode;
}) {
  const anchor = n.x > 0.5 ? "start" : n.x < -0.5 ? "end" : "middle";
  return (
    <Label x={(a.x + b.x) / 2} y={(a.y + b.y) / 2} dx={n.x * 6} dy={n.y * 10} anchor={anchor} small={small}>
      {children}
    </Label>
  );
}

/** The closed outline: the picked walls solid and labelled, the wall under
 *  the cursor thick (red when it can't be picked), the rest faint. With a
 *  scale, every wall carries its length, small, inside the room: beside the
 *  label on a picked wall. */
function Outline({ corners, solid, candidate, candidateRefused, scale }: {
  corners: Frac[]; solid: { wall: number; label: string }[]; candidate: number | null; candidateRefused: boolean;
  scale: GuideScale | null;
}) {
  const size = scale?.size ?? { w: 1, h: 1 };
  const inward: 1 | -1 = signedArea2(corners, size) > 0 ? 1 : -1;
  return (
    <>
      {corners.map((_, i) => {
        const [a, b] = wallEnds(corners, i);
        const picked = solid.find((s) => s.wall === i);
        const n = normalOf(a, b, size, inward);
        const length = scale && (a.x !== b.x || a.y !== b.y) ? `${formatMetres(wallLengthM(a, b, scale.size, scale.pxPerM))} m` : null;
        if (picked) {
          return (
            <g key={i}>
              <Line a={a} b={b} color={ACCENT} width={2.5} />
              <SideText a={a} b={b} n={n}>
                {picked.label}
                {length && <tspan dx={6} fill={MUTED} style={{ fontSize: SMALL_FONT }}>{length}</tspan>}
              </SideText>
            </g>
          );
        }
        return (
          <g key={i}>
            {i === candidate
              ? <Line a={a} b={b} color={candidateRefused ? DANGER : ACCENT} width={4} opacity={0.8} />
              : <Line a={a} b={b} color={MUTED} width={1.5} dash="4 4" opacity={0.6} />}
            {length && <SideText a={a} b={b} n={n} small>{length}</SideText>}
          </g>
        );
      })}
    </>
  );
}

/** The text in the place dialog's X and Y boxes, which of them were typed
 *  in, and the clicked point, whose side of each wall a typed distance keeps. */
export interface TypedDistances { x: string; y: string; xEdited: boolean; yEdited: boolean; from: Frac }

/** The place dialog's X and Y boxes (D1.6), filled from the clicked point.
 *  `reads` is what the guides read for the point now, so a distance past the
 *  image's edge (the point is clamped) says where the image ends. */
export function PlaceDistanceFields({ typed, reads, onType }: {
  typed: TypedDistances;
  reads: Distances | null;
  onType: (axis: "x" | "y", text: string) => void;
}) {
  const field = (axis: "x" | "y") => {
    const text = typed[axis];
    const value = parseMetres(text);
    const edited = axis === "x" ? typed.xEdited : typed.yEdited;
    const bad = edited && value === null;
    const now = reads ? reads[axis] : null;
    const clamped = edited && value !== null && now !== null && Math.abs(now - value) > 0.005;
    return (
      <div className="flex-1 min-w-0 space-y-1">
        <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">{axis.toUpperCase()} (m)</label>
        <input type="text" inputMode="decimal" value={text} aria-label={`${axis.toUpperCase()} in metres from the ${axis.toUpperCase()} wall`}
          onChange={(e) => onType(axis, e.target.value)}
          className="w-full bg-s-elevated border rounded-lg px-3 py-2 text-sm font-mono text-s-text focus:outline-none focus:border-s-accent transition-colors"
          style={{ borderColor: bad ? "var(--danger, #ef4444)" : "var(--border)" }} />
        {bad && <p style={{ color: "var(--danger, #ef4444)", fontSize: 11 }}>Metres, e.g. 2.50</p>}
        {clamped && now !== null && (
          <p className="font-mono text-[10px]" style={{ color: "var(--warning, #f59e0b)" }}>
            The image ends {formatMetres(now)} m from this wall
          </p>
        )}
      </div>
    );
  };
  return (
    <div className="space-y-1">
      <div className="flex gap-2">{field("x")}{field("y")}</div>
      <p className="font-mono text-[10px] text-s-muted">From the X and Y walls, square to each. Typing moves the point.</p>
    </div>
  );
}

/** One dimension line, from a wall's foot to the point: the wall's line
 *  extended faintly to the foot when the foot is past the wall's end, the dot,
 *  the line, and its label (above a mostly level line, right of an upright one,
 *  as the rectangle's were). */
function Guide({ foot, extension, point, text, size }: {
  foot: Frac; extension: [Frac, Frac] | null; point: Frac; text: string; size: ImageSize;
}) {
  const level = Math.abs((point.x - foot.x) * size.w) >= Math.abs((point.y - foot.y) * size.h);
  const mid = { x: (foot.x + point.x) / 2, y: (foot.y + point.y) / 2 };
  return (
    <>
      {extension && <Line a={extension[0]} b={extension[1]} color={ACCENT} width={1.5} dash="3 4" opacity={0.5} />}
      <Line a={foot} b={point} color={ACCENT} width={1.5} />
      <circle cx={pct(foot.x)} cy={pct(foot.y)} r={4} fill={ACCENT} stroke={HALO} strokeWidth={1.5} />
      {level
        ? <Label x={mid.x} y={mid.y} dy={-9}>{text}</Label>
        : <Label x={mid.x} y={mid.y} dx={8} anchor="start">{text}</Label>}
    </>
  );
}

/** The whole overlay over the map. While a step is running it shows that
 *  step; otherwise the saved walls and, for `point`, the two guides. With a
 *  scale, walls carry their lengths in metres: the wall being drawn live, the
 *  others small. */
export function WallGuidesOverlay({ walls, setup, point, distances, scale }: {
  walls: WallGuides | null;
  setup: {
    step: WallStep | null; corners: Frac[]; cursor: Frac | null; outline: Frac[] | null;
    xWall: number | null; candidate: number | null; candidateRefused: boolean;
  };
  point: Frac | null;
  distances: Distances | null;
  scale: GuideScale | null;
}) {
  if (setup.step === 1) {
    const pts = setup.corners, size = scale?.size ?? { w: 1, h: 1 };
    const last = pts[pts.length - 1];
    const live = last && setup.cursor && (last.x !== setup.cursor.x || last.y !== setup.cursor.y) ? setup.cursor : null;
    return (
      <>
        <PolygonDraftPreview points={pts} cursor={setup.cursor} />
        {scale && (
          <svg className="absolute inset-0 w-full h-full" style={{ pointerEvents: "none", overflow: "visible", zIndex: 5 }} aria-hidden="true">
            {pts.slice(1).map((b, i) => {
              const a = pts[i];
              if (a.x === b.x && a.y === b.y) return null;
              return <SideText key={i} a={a} b={b} n={normalOf(a, b, size, null)} small>{`${formatMetres(wallLengthM(a, b, scale.size, scale.pxPerM))} m`}</SideText>;
            })}
            {live && (
              <SideText a={last} b={live} n={normalOf(last, live, size, null)}>{`${formatMetres(wallLengthM(last, live, scale.size, scale.pxPerM))} m`}</SideText>
            )}
          </svg>
        )}
        <PolygonDraftHint count={pts.length} />
      </>
    );
  }
  let content: React.ReactNode = null;
  if (setup.step !== null && setup.outline) {
    content = (
      <Outline corners={setup.outline} solid={setup.xWall !== null ? [{ wall: setup.xWall, label: "X wall" }] : []}
        candidate={setup.candidate} candidateRefused={setup.candidateRefused} scale={scale} />
    );
  } else if (setup.step === null && walls) {
    const outline = (
      <Outline corners={walls.corners} solid={[{ wall: walls.xWall, label: "X wall" }, { wall: walls.yWall, label: "Y wall" }]}
        candidate={null} candidateRefused={false} scale={scale} />
    );
    let guides: React.ReactNode = null;
    if (point && distances && scale) {
      const g = guideGeometry(walls, point, scale.size);
      guides = (
        <g opacity={g.inside ? 1 : 0.45}>
          <Guide foot={g.x.foot} extension={g.x.extension} point={point} text={`X ${formatMetres(distances.x)} m`} size={scale.size} />
          <Guide foot={g.y.foot} extension={g.y.extension} point={point} text={`Y ${formatMetres(distances.y)} m`} size={scale.size} />
        </g>
      );
    }
    content = <>{outline}{guides}</>;
  }
  if (!content) return null;
  return (
    <svg className="absolute inset-0 w-full h-full" style={{ pointerEvents: "none", overflow: "visible", zIndex: 5 }}
      aria-hidden="true">
      {content}
    </svg>
  );
}
