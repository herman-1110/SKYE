// Placement guides for Manage Devices (Prompt 143, D1, as changed on 18 Nov).
// Herman draws the room's outline corner by corner, the way a zone is drawn,
// so a room can have any number of corners and slanted walls. Each wall is the
// straight edge between two corners. He picks one wall as the X wall and
// another, more than 30 degrees from parallel to it, as the Y wall. A device's
// X and Y are its distances from those two walls in metres, measured square to
// each wall, to the wall's line extended past its ends where needed.
//
// Pure maths with no imports, so tools/harness/f143_wall_guides_check.ts can
// run it under Node as it is. Points are fractions of the image (0-1), like an
// AP's x_pct and y_pct. Lengths, distances and angles are worked out in the
// image's pixels, since x and y fractions have different scales unless the
// image is square. Metres use the backend's numbers
// (floor_service.derive_ap_metres): pixels from image_width_px and
// image_height_px, divided by the floor's px/m. An upright or level wall uses
// the rectangle's arithmetic from before, so a rectangular room reads exactly
// as it did with the rectangle (commits 9 and 11).

export interface Frac { x: number; y: number }

/** The image's size in pixels. */
export interface ImageSize { w: number; h: number }

/** X and Y in metres. */
export interface Distances { x: number; y: number }

/** The room's outline and the two walls picked on it. Wall i is the edge from
 *  corners[i] to corners[(i + 1) % corners.length]. */
export interface WallGuides { corners: Frac[]; xWall: number; yWall: number }

/** Saved per floor in this browser's localStorage, under this prefix plus the floor id. */
export const WALL_GUIDES_KEY_PREFIX = "skye-wall-guides:";

export function wallGuidesKey(floorId: string): string {
  return WALL_GUIDES_KEY_PREFIX + floorId;
}

/** The Y wall must be more than this many degrees from parallel to the X wall. */
export const MIN_WALL_ANGLE_DEG = 30;

export function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/** Wall i's two ends. */
export function wallEnds(corners: Frac[], i: number): [Frac, Frac] {
  return [corners[i], corners[(i + 1) % corners.length]];
}

const isDot = (a: Frac, b: Frac) => a.x === b.x && a.y === b.y;
const isUpright = (a: Frac, b: Frac) => a.x === b.x && a.y !== b.y;
const isLevel = (a: Frac, b: Frac) => a.y === b.y && a.x !== b.x;

/** A wall's length in metres. A level or upright wall uses the rectangle's
 *  arithmetic, |Δx| × width ÷ px/m or |Δy| × height ÷ px/m. */
export function wallLengthM(a: Frac, b: Frac, size: ImageSize, pxPerM: number): number {
  if (a.y === b.y) return Math.abs(b.x - a.x) * size.w / pxPerM;
  if (a.x === b.x) return Math.abs(b.y - a.y) * size.h / pxPerM;
  return Math.hypot((b.x - a.x) * size.w, (b.y - a.y) * size.h) / pxPerM;
}

/** The distance from p to the wall's line, square to the wall, in metres. An
 *  upright wall gives |x − wall's x| × width ÷ px/m and a level one
 *  |y − wall's y| × height ÷ px/m: derive_ap_metres()'s arithmetic, measured
 *  from the wall, as the rectangle had it. */
export function distanceToWallM(a: Frac, b: Frac, p: Frac, size: ImageSize, pxPerM: number): number {
  if (a.x === b.x) return Math.abs(p.x - a.x) * size.w / pxPerM;
  if (a.y === b.y) return Math.abs(p.y - a.y) * size.h / pxPerM;
  const dx = (b.x - a.x) * size.w, dy = (b.y - a.y) * size.h;
  const px = (p.x - a.x) * size.w, py = (p.y - a.y) * size.h;
  return Math.abs(dx * py - dy * px) / Math.hypot(dx, dy) / pxPerM;
}

/** X and Y for a point: its distances from the X wall and the Y wall. */
export function distancesM(g: WallGuides, p: Frac, size: ImageSize, pxPerM: number): Distances {
  const [xa, xb] = wallEnds(g.corners, g.xWall), [ya, yb] = wallEnds(g.corners, g.yWall);
  return { x: distanceToWallM(xa, xb, p, size, pxPerM), y: distanceToWallM(ya, yb, p, size, pxPerM) };
}

/** Twice the outline's signed area in image pixels: positive when its corners
 *  run clockwise on screen (y grows downward). */
export function signedArea2(corners: Frac[], size: ImageSize): number {
  let s = 0;
  for (let i = 0; i < corners.length; i++) {
    const [a, b] = wallEnds(corners, i);
    s += a.x * b.y - b.x * a.y;
  }
  return s * size.w * size.h;
}

/** Which side of wall i's line p is on: 1 the room's side, -1 the other, 0 on the line. */
export function sideOfWall(corners: Frac[], i: number, p: Frac, size: ImageSize): -1 | 0 | 1 {
  const [a, b] = wallEnds(corners, i);
  // The cross product's sign is the same in fractions as in pixels, and exact for an upright or level wall.
  const cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
  if (cross === 0) return 0;
  return (cross > 0) === (signedArea2(corners, size) > 0) ? 1 : -1;
}

/** Wall i's unit normal pointing into the room, in image pixels (y down). */
export function inwardNormal(corners: Frac[], i: number, size: ImageSize): { x: number; y: number } {
  const [a, b] = wallEnds(corners, i);
  const dx = (b.x - a.x) * size.w, dy = (b.y - a.y) * size.h;
  const len = Math.hypot(dx, dy) || 1;
  const s = signedArea2(corners, size) > 0 ? 1 : -1;
  return { x: (-dy / len) * s, y: (dx / len) * s };
}

/** Where the square line from p meets the wall's line, and how far along the
 *  wall that is: t is 0 at a and 1 at b; outside 0-1 the foot is on the line
 *  extended past an end. */
export function footOnWall(a: Frac, b: Frac, p: Frac, size: ImageSize): { foot: Frac; t: number } {
  if (isDot(a, b)) return { foot: { x: a.x, y: a.y }, t: 0 };
  if (a.x === b.x) return { foot: { x: a.x, y: p.y }, t: (p.y - a.y) / (b.y - a.y) };
  if (a.y === b.y) return { foot: { x: p.x, y: a.y }, t: (p.x - a.x) / (b.x - a.x) };
  const dx = (b.x - a.x) * size.w, dy = (b.y - a.y) * size.h;
  const t = ((p.x - a.x) * size.w * dx + (p.y - a.y) * size.h * dy) / (dx * dx + dy * dy);
  return { foot: { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) }, t };
}

/** Whether p is inside the outline; a point on a wall counts as inside. */
export function insideOutline(corners: Frac[], p: Frac): boolean {
  let inside = false;
  for (let i = 0, j = corners.length - 1; i < corners.length; j = i++) {
    const a = corners[j], b = corners[i];
    const cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x);
    if (Math.abs(cross) <= 1e-12 && p.x >= Math.min(a.x, b.x) && p.x <= Math.max(a.x, b.x)
      && p.y >= Math.min(a.y, b.y) && p.y <= Math.max(a.y, b.y)) return true;
    if ((a.y > p.y) !== (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

/** One wall's guide to a point: the foot of the square line on the wall's
 *  line, and the stretch the wall is extended by to reach it (from its nearer
 *  end) when the foot is past an end, else null. */
export interface WallGuide { foot: Frac; extension: [Frac, Frac] | null }

/** What the drawing needs for one point: each wall's guide, and whether the
 *  point is inside the room (outside, the guides are drawn fainter). */
export interface GuideGeometry { x: WallGuide; y: WallGuide; inside: boolean }

export function guideGeometry(g: WallGuides, p: Frac, size: ImageSize): GuideGeometry {
  const guide = (i: number): WallGuide => {
    const [a, b] = wallEnds(g.corners, i);
    const { foot, t } = footOnWall(a, b, p, size);
    return { foot, extension: t < 0 ? [a, foot] : t > 1 ? [b, foot] : null };
  };
  return { x: guide(g.xWall), y: guide(g.yWall), inside: insideOutline(g.corners, p) };
}

/** Where typed distances put a device (D1.6): its distance from the X wall's
 *  line is X and from the Y wall's line is Y, on the same side of each wall as
 *  `from` (the clicked point), or the room's side when `from` is on that
 *  wall's line. A distance left null keeps `current`'s distance to that wall.
 *  Clamped to the image. An upright X wall with a level Y wall, or the other
 *  way round, works on the coordinates directly, as the rectangle did, so a
 *  rectangle gives exactly its results (and a null distance keeps `current`'s
 *  coordinate). */
export function placeAtDistances(g: WallGuides, from: Frac, current: Frac, typed: { x: number | null; y: number | null },
                                 size: ImageSize, pxPerM: number): Frac {
  const [xa, xb] = wallEnds(g.corners, g.xWall), [ya, yb] = wallEnds(g.corners, g.yWall);
  const sideX = sideOfWall(g.corners, g.xWall, from, size) || 1;
  const sideY = sideOfWall(g.corners, g.yWall, from, size) || 1;
  const nX = inwardNormal(g.corners, g.xWall, size), nY = inwardNormal(g.corners, g.yWall, size);
  if (isUpright(xa, xb) && isLevel(ya, yb)) {
    const sx = Math.sign(nX.x) * sideX, sy = Math.sign(nY.y) * sideY;
    return {
      x: typed.x !== null ? clamp01(xa.x + sx * typed.x * pxPerM / size.w) : current.x,
      y: typed.y !== null ? clamp01(ya.y + sy * typed.y * pxPerM / size.h) : current.y,
    };
  }
  if (isLevel(xa, xb) && isUpright(ya, yb)) {
    const sy = Math.sign(nX.y) * sideX, sx = Math.sign(nY.x) * sideY;
    return {
      x: typed.y !== null ? clamp01(ya.x + sx * typed.y * pxPerM / size.w) : current.x,
      y: typed.x !== null ? clamp01(xa.y + sy * typed.x * pxPerM / size.h) : current.y,
    };
  }
  // In general: each wall's line, moved its distance towards the chosen side; the two meet at the point.
  const dX = (typed.x ?? distanceToWallM(xa, xb, current, size, pxPerM)) * pxPerM;
  const dY = (typed.y ?? distanceToWallM(ya, yb, current, size, pxPerM)) * pxPerM;
  const mX = { x: nX.x * sideX, y: nX.y * sideX }, mY = { x: nY.x * sideY, y: nY.y * sideY };
  const cX = dX + mX.x * xa.x * size.w + mX.y * xa.y * size.h;
  const cY = dY + mY.x * ya.x * size.w + mY.y * ya.y * size.h;
  const det = mX.x * mY.y - mX.y * mY.x;
  return {
    x: clamp01((cX * mY.y - mX.y * cY) / det / size.w),
    y: clamp01((mX.x * cY - cX * mY.x) / det / size.h),
  };
}

/** The wall nearest p, measured to the wall itself in image pixels; a wall
 *  with no length is skipped. Null when there's none. */
export function nearestWall(corners: Frac[], p: Frac, size: ImageSize): number | null {
  let best: number | null = null, bestD = Infinity;
  for (let i = 0; i < corners.length; i++) {
    const [a, b] = wallEnds(corners, i);
    if (isDot(a, b)) continue;
    const { t } = footOnWall(a, b, p, size);
    const c = t <= 0 ? a : t >= 1 ? b : { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) };
    const d = Math.hypot((p.x - c.x) * size.w, (p.y - c.y) * size.h);
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

/** The angle between two walls' lines in image pixels, 0 to 90 degrees. */
export function wallAngleDeg(corners: Frac[], i: number, j: number, size: ImageSize): number {
  const [a, b] = wallEnds(corners, i), [c, d] = wallEnds(corners, j);
  const ux = (b.x - a.x) * size.w, uy = (b.y - a.y) * size.h;
  const vx = (d.x - c.x) * size.w, vy = (d.y - c.y) * size.h;
  return Math.atan2(Math.abs(ux * vy - uy * vx), Math.abs(ux * vx + uy * vy)) * 180 / Math.PI;
}

/** Whether wall j can be the Y wall with wall i as the X wall: another wall,
 *  with a length, more than 30 degrees from parallel to it. */
export function canPairWalls(corners: Frac[], i: number, j: number, size: ImageSize): boolean {
  if (i === j) return false;
  const [a, b] = wallEnds(corners, i), [c, d] = wallEnds(corners, j);
  if (isDot(a, b) || isDot(c, d)) return false;
  return wallAngleDeg(corners, i, j, size) > MIN_WALL_ANGLE_DEG + 1e-9;
}

/** Shift while drawing the walls: the corner placed so the edge from `last`
 *  is level or upright, whichever is nearer in pixels, and lined up with the
 *  first corner when it comes within `tol` (fractions) of it, so the outline
 *  can close square. Pass first only once there are two corners or more. */
export function snapCorner(last: Frac, p: Frac, size: ImageSize, first: Frac | null, tol: Frac): Frac {
  if (Math.abs((p.x - last.x) * size.w) >= Math.abs((p.y - last.y) * size.h)) {
    return { x: first && Math.abs(p.x - first.x) <= tol.x ? first.x : p.x, y: last.y };
  }
  return { x: last.x, y: first && Math.abs(p.y - first.y) <= tol.y ? first.y : p.y };
}

/** Metres to 2 decimal places, as the guides show them. */
export function formatMetres(m: number): string {
  return m.toFixed(2);
}

/** A typed distance in metres ("2", "2.", "2.5", ".5"), or null when it isn't
 *  one. Negative numbers aren't distances. */
export function parseMetres(text: string): number | null {
  const t = text.trim();
  if (!/^(\d+\.?\d*|\.\d+)$/.test(t)) return null;
  const v = Number(t);
  return Number.isFinite(v) ? v : null;
}

/** The pixel size the metres are counted in: the floor's image_width_px and
 *  image_height_px, as derive_ap_metres() uses, or the image's natural size
 *  when the floor lacks either. Null when neither is known yet. */
export function guideImageSize(
  floor: { image_width_px?: number | null; image_height_px?: number | null },
  natural: ImageSize | null,
): ImageSize | null {
  const w = floor.image_width_px, h = floor.image_height_px;
  if (typeof w === "number" && w > 0 && typeof h === "number" && h > 0) return { w, h };
  if (natural && natural.w > 0 && natural.h > 0) return natural;
  return null;
}

/** The walls as saved: the outline's corners and the two walls picked (v 2). */
export function serialiseWallGuides(g: WallGuides): string {
  return JSON.stringify({ v: 2, corners: g.corners.map((c) => ({ x: c.x, y: c.y })), xWall: g.xWall, yWall: g.yWall });
}

/** Saved walls read back, or null for anything that isn't a valid v 2 save.
 *  The rectangle saves from before (v 1) read as no walls, so they're drawn again. */
export function parseWallGuides(raw: string | null | undefined): WallGuides | null {
  if (!raw) return null;
  let o: unknown;
  try {
    o = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!o || typeof o !== "object") return null;
  const { v, corners, xWall, yWall } = o as { v?: unknown; corners?: unknown; xWall?: unknown; yWall?: unknown };
  if (v !== 2 || !Array.isArray(corners) || corners.length < 3 || corners.length > 500) return null;
  const ok = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 1;
  const pts: Frac[] = [];
  for (const c of corners) {
    if (!c || typeof c !== "object") return null;
    const { x, y } = c as { x?: unknown; y?: unknown };
    if (!ok(x) || !ok(y)) return null;
    pts.push({ x, y });
  }
  const index = (n: unknown): n is number => typeof n === "number" && Number.isInteger(n) && n >= 0 && n < pts.length;
  if (!index(xWall) || !index(yWall) || xWall === yWall) return null;
  const [a, b] = wallEnds(pts, xWall), [c, d] = wallEnds(pts, yWall);
  if (isDot(a, b) || isDot(c, d)) return null;
  return { corners: pts, xWall, yWall };
}
