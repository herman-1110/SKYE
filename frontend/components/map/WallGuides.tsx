"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  formatMetres, guideGeometry, nearerEndWall, nearerSideWall, parseMetres, parseWallGuides, rectFromCorners,
  rectSizeM, serialiseWallGuides, wallGuidesKey,
  type Distances, type EndWall, type Frac, type ImageSize, type SideWall, type WallGuides, type WallRect,
} from "@/utils/wallGuides";

// Placement guides for Manage Devices (Prompt 143, D1): the walls Herman picks,
// drawn over the floor plan, and two dimension lines from them to the device
// being placed, dragged or hovered. The room's outline carries its width and
// height in metres. The maths is in utils/wallGuides.ts.
// Everything is drawn in percentages of the image, so the overlay needs no
// measuring; only line widths and text are in pixels.

const ACCENT = "var(--accent)";
const MUTED = "var(--text-secondary)";
const HALO = "var(--bg-surface)";
const SMALL_FONT = 10;
const pct = (v: number) => `${v * 100}%`;

/** What metres are counted in: the image's pixel size and the floor's px/m. */
export interface GuideScale { size: ImageSize; pxPerM: number }

/** The room's width and height as shown, "6.10 m"; null without a scale. */
interface RoomLengths { w: string; h: string }

function roomLengths(rect: WallRect, scale: GuideScale | null): RoomLengths | null {
  if (!scale) return null;
  const m = rectSizeM(rect, scale.size, scale.pxPerM);
  return { w: `${formatMetres(m.w)} m`, h: `${formatMetres(m.h)} m` };
}

export type WallStep = 1 | 2 | 3;

export const WALL_STEP_HINT: Record<WallStep, string> = {
  1: "Walls, step 1 of 3: drag a rectangle over the room. Esc cancels.",
  2: "Step 2 of 3: click the room's left or right wall. That's the X wall. Esc cancels.",
  3: "Step 3 of 3: click its top or bottom wall. That's the Y wall. Esc cancels.",
};

/** The walls kept for this floor in this browser (D1.7), with a save and a
 *  clear. Every storage access is wrapped, like skye-theme in app/layout.tsx:
 *  where storage is blocked the walls still work, they just aren't kept. */
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

/** The three steps (D1.2): drag a rectangle, click a side wall, click the top
 *  or bottom wall. The editor passes its map's pointer events in, as fractions
 *  of the image; Esc cancels at any step and keeps the walls there were. */
export function useWallSetup(onDone: (g: WallGuides) => void) {
  const [step, setStep] = useState<WallStep | null>(null);
  const [corner, setCorner] = useState<Frac | null>(null);   // where step 1's drag began
  const [rect, setRect] = useState<WallRect | null>(null);
  const [xWall, setXWall] = useState<SideWall | null>(null);
  const [hover, setHover] = useState<Frac | null>(null);
  // Step 1's drag ends on a corner, which lies on a side wall and an end wall
  // at once, so the click that follows its pointerup mustn't count as step 2.
  // A new gesture starts with a pointerdown, which resets it.
  const swallowClick = useRef(false);

  const reset = useCallback(() => {
    setStep(null); setCorner(null); setRect(null); setXWall(null); setHover(null);
  }, []);

  useEffect(() => {
    if (step === null) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") reset(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, reset]);

  const start = () => { reset(); setStep(1); };

  const pointerDown = (p: Frac, e: React.PointerEvent<HTMLElement>) => {
    swallowClick.current = false;
    if (step !== 1) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setCorner(p);
    setRect(rectFromCorners(p, p));
  };

  const pointerMove = (p: Frac) => {
    setHover(p);
    if (step === 1 && corner) setRect(rectFromCorners(corner, p));
  };

  /** min: the smallest rectangle that counts, in fractions (a few pixels). */
  const pointerUp = (p: Frac, min: { w: number; h: number }) => {
    if (step !== 1 || !corner) return;
    const r = rectFromCorners(corner, p);
    setCorner(null);
    swallowClick.current = true;
    if (r.x1 - r.x0 < min.w || r.y1 - r.y0 < min.h) { setRect(null); return; }   // too small: drag again
    setRect(r);
    setStep(2);
  };

  const click = (p: Frac) => {
    if (swallowClick.current) { swallowClick.current = false; return; }
    if (step === 2 && rect) {
      setXWall(nearerSideWall(rect, p));
      setStep(3);
    } else if (step === 3 && rect && xWall) {
      onDone({ rect, xWall, yWall: nearerEndWall(rect, p) });
      reset();
    }
  };

  // The wall a click would pick now, highlighted as the cursor moves.
  const candidate: SideWall | EndWall | null =
    step === 2 && rect && hover ? nearerSideWall(rect, hover)
      : step === 3 && rect && hover ? nearerEndWall(rect, hover)
        : null;

  return { step, rect, xWall, candidate, start, cancel: reset, pointerDown, pointerMove, pointerUp, click };
}

/** A label over the plan; `small` ones are muted, like the room's lengths. */
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

function wallLine(rect: WallRect, wall: SideWall | EndWall): { x1: number; y1: number; x2: number; y2: number } {
  if (wall === "left" || wall === "right") {
    const x = wall === "left" ? rect.x0 : rect.x1;
    return { x1: x, y1: rect.y0, x2: x, y2: rect.y1 };
  }
  const y = wall === "top" ? rect.y0 : rect.y1;
  return { x1: rect.x0, y1: y, x2: rect.x1, y2: y };
}

/** Text just inside the rectangle by a wall's midpoint: its label, or a length. */
function WallText({ rect, wall, small = false, children }: {
  rect: WallRect; wall: SideWall | EndWall; small?: boolean; children: React.ReactNode;
}) {
  const midX = (rect.x0 + rect.x1) / 2, midY = (rect.y0 + rect.y1) / 2;
  if (wall === "left") return <Label x={rect.x0} y={midY} dx={6} anchor="start" small={small}>{children}</Label>;
  if (wall === "right") return <Label x={rect.x1} y={midY} dx={-6} anchor="end" small={small}>{children}</Label>;
  if (wall === "top") return <Label x={midX} y={rect.y0} dy={10} small={small}>{children}</Label>;
  return <Label x={midX} y={rect.y1} dy={-10} small={small}>{children}</Label>;
}

const isSideWall = (w: SideWall | EndWall): w is SideWall => w === "left" || w === "right";

function Line({ l, color, width, dash, opacity = 1 }: {
  l: { x1: number; y1: number; x2: number; y2: number }; color: string; width: number; dash?: string; opacity?: number;
}) {
  return (
    <line x1={pct(l.x1)} y1={pct(l.y1)} x2={pct(l.x2)} y2={pct(l.y2)}
      stroke={color} strokeWidth={width} strokeDasharray={dash} strokeLinecap="round" opacity={opacity} />
  );
}

/** The rectangle with its four sides: `solid` ones drawn and labelled, the
 *  rest faint, and `candidate` (the wall a click would pick) thick. With
 *  `lengths`, the room's height sits small beside the side wall's label and
 *  its width beside the end wall's; until a wall of that kind is picked, the
 *  width sits on the top edge and the height on the left one. */
function Room({ rect, solid, candidate, lengths }: {
  rect: WallRect; solid: { wall: SideWall | EndWall; label: string }[]; candidate: SideWall | EndWall | null;
  lengths: RoomLengths | null;
}) {
  const walls: (SideWall | EndWall)[] = ["left", "right", "top", "bottom"];
  return (
    <>
      {walls.filter((w) => !solid.some((s) => s.wall === w) && w !== candidate).map((w) => (
        <Line key={w} l={wallLine(rect, w)} color={MUTED} width={1.5} dash="4 4" opacity={0.6} />
      ))}
      {candidate && !solid.some((s) => s.wall === candidate) && (
        <Line l={wallLine(rect, candidate)} color={ACCENT} width={4} opacity={0.8} />
      )}
      {solid.map((s) => (
        <g key={s.wall}>
          <Line l={wallLine(rect, s.wall)} color={ACCENT} width={2.5} />
          <WallText rect={rect} wall={s.wall}>
            {s.label}
            {lengths && (
              <tspan dx={6} fill={MUTED} style={{ fontSize: SMALL_FONT }}>{isSideWall(s.wall) ? lengths.h : lengths.w}</tspan>
            )}
          </WallText>
        </g>
      ))}
      {lengths && !solid.some((s) => !isSideWall(s.wall)) && <WallText rect={rect} wall="top" small>{lengths.w}</WallText>}
      {lengths && !solid.some((s) => isSideWall(s.wall)) && <WallText rect={rect} wall="left" small>{lengths.h}</WallText>}
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
      <p className="font-mono text-[10px] text-s-muted">From the X and Y walls. Typing moves the point.</p>
    </div>
  );
}

/** The whole overlay over the map. While a step is running it shows that
 *  step; otherwise the saved walls and, for `point`, the two guides. With a
 *  `scale`, the room's outline carries its width and height in metres: live
 *  while step 1's rectangle is being drawn, then small beside the walls' labels. */
export function WallGuidesOverlay({ walls, setup, point, distances, scale }: {
  walls: WallGuides | null;
  setup: { step: WallStep | null; rect: WallRect | null; xWall: SideWall | null; candidate: SideWall | EndWall | null };
  point: Frac | null;
  distances: Distances | null;
  scale: GuideScale | null;
}) {
  let content: React.ReactNode = null;
  if (setup.step !== null) {
    const r = setup.rect;
    if (setup.step === 1 && r) {
      // The width on the top edge and the height on the left one, as the drag goes (none for the press's 0 x 0)
      const live = r.x1 > r.x0 || r.y1 > r.y0 ? roomLengths(r, scale) : null;
      content = (
        <>
          <rect x={pct(r.x0)} y={pct(r.y0)} width={pct(r.x1 - r.x0)} height={pct(r.y1 - r.y0)}
            fill="none" stroke={ACCENT} strokeWidth={2} strokeDasharray="6 4" />
          {live && <WallText rect={r} wall="top">{live.w}</WallText>}
          {live && <WallText rect={r} wall="left">{live.h}</WallText>}
        </>
      );
    } else if (r) {
      content = <Room rect={r} solid={setup.xWall ? [{ wall: setup.xWall, label: "X wall" }] : []} candidate={setup.candidate}
        lengths={roomLengths(r, scale)} />;
    }
  } else if (walls) {
    const room = <Room rect={walls.rect} solid={[{ wall: walls.xWall, label: "X wall" }, { wall: walls.yWall, label: "Y wall" }]} candidate={null}
      lengths={roomLengths(walls.rect, scale)} />;
    let guides: React.ReactNode = null;
    if (point && distances) {
      const g = guideGeometry(walls, point);
      const opacity = g.inside ? 1 : 0.45;
      guides = (
        <g opacity={opacity}>
          {g.xWallExtension && (
            <Line l={{ x1: g.wallX, y1: g.xWallExtension[0], x2: g.wallX, y2: g.xWallExtension[1] }} color={ACCENT} width={1.5} dash="3 4" />
          )}
          {g.yWallExtension && (
            <Line l={{ x1: g.yWallExtension[0], y1: g.wallY, x2: g.yWallExtension[1], y2: g.wallY }} color={ACCENT} width={1.5} dash="3 4" />
          )}
          <Line l={{ x1: g.xDot.x, y1: g.xDot.y, x2: point.x, y2: point.y }} color={ACCENT} width={1.5} />
          <Line l={{ x1: g.yDot.x, y1: g.yDot.y, x2: point.x, y2: point.y }} color={ACCENT} width={1.5} />
          <circle cx={pct(g.xDot.x)} cy={pct(g.xDot.y)} r={4} fill={ACCENT} stroke={HALO} strokeWidth={1.5} />
          <circle cx={pct(g.yDot.x)} cy={pct(g.yDot.y)} r={4} fill={ACCENT} stroke={HALO} strokeWidth={1.5} />
          <Label x={(g.xDot.x + point.x) / 2} y={point.y} dy={-9}>{`X ${formatMetres(distances.x)} m`}</Label>
          <Label x={point.x} y={(g.yDot.y + point.y) / 2} dx={8} anchor="start">{`Y ${formatMetres(distances.y)} m`}</Label>
        </g>
      );
    }
    content = <>{room}{guides}</>;
  }
  if (!content) return null;
  return (
    <svg className="absolute inset-0 w-full h-full" style={{ pointerEvents: "none", overflow: "visible", zIndex: 5 }}
      aria-hidden="true">
      {content}
    </svg>
  );
}
