// Placement guides for Manage Devices (Prompt 143, D1). Herman draws a
// rectangle over the room, then picks one of its side walls (the X wall) and
// its top or bottom wall (the Y wall). A device's X and Y are its distances
// from those two walls, in metres.
//
// Pure maths with no imports, so tools/harness/f143_wall_guides_check.ts can
// run it under Node as it is. Points are fractions of the image (0-1), like an
// AP's x_pct and y_pct. Metres use the backend's numbers
// (floor_service.derive_ap_metres): a fraction times image_width_px (or
// image_height_px), divided by the floor's px/m.

export interface Frac { x: number; y: number }

/** An axis-aligned rectangle in fractions of the image, with x0 < x1 and y0 < y1. */
export interface WallRect { x0: number; y0: number; x1: number; y1: number }

export type SideWall = "left" | "right";
export type EndWall = "top" | "bottom";

/** The rectangle and the two walls picked on it. */
export interface WallGuides { rect: WallRect; xWall: SideWall; yWall: EndWall }

/** The image's size in pixels. */
export interface ImageSize { w: number; h: number }

/** X and Y in metres. */
export interface Distances { x: number; y: number }

/** Saved per floor in this browser's localStorage, under this prefix plus the floor id. */
export const WALL_GUIDES_KEY_PREFIX = "skye-wall-guides:";

export function wallGuidesKey(floorId: string): string {
  return WALL_GUIDES_KEY_PREFIX + floorId;
}

export function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

/** The rectangle two drag corners span, clamped to the image. */
export function rectFromCorners(a: Frac, b: Frac): WallRect {
  const ax = clamp01(a.x), ay = clamp01(a.y), bx = clamp01(b.x), by = clamp01(b.y);
  return { x0: Math.min(ax, bx), y0: Math.min(ay, by), x1: Math.max(ax, bx), y1: Math.max(ay, by) };
}

/** The X wall's place across the image (a fraction of its width). */
export function xWallAt(g: WallGuides): number {
  return g.xWall === "left" ? g.rect.x0 : g.rect.x1;
}

/** The Y wall's place down the image (a fraction of its height). */
export function yWallAt(g: WallGuides): number {
  return g.yWall === "top" ? g.rect.y0 : g.rect.y1;
}

export function insideRect(rect: WallRect, p: Frac): boolean {
  return p.x >= rect.x0 && p.x <= rect.x1 && p.y >= rect.y0 && p.y <= rect.y1;
}

/** X = |x − X wall| × width ÷ px/m and Y = |y − Y wall| × height ÷ px/m:
 *  derive_ap_metres()'s arithmetic, measured from the walls instead of the
 *  image's top left corner. */
export function distancesM(g: WallGuides, p: Frac, size: ImageSize, pxPerM: number): Distances {
  return {
    x: Math.abs(p.x - xWallAt(g)) * size.w / pxPerM,
    y: Math.abs(p.y - yWallAt(g)) * size.h / pxPerM,
  };
}

/** Where typed distances put a device, measured from the same walls. Each
 *  axis keeps the side of its wall that `from` (the clicked point) is on; a
 *  point right on the wall goes into the room. Clamped to the image. */
export function pointAtDistances(g: WallGuides, from: Frac, d: Distances, size: ImageSize, pxPerM: number): Frac {
  const wx = xWallAt(g), wy = yWallAt(g);
  const sx = from.x > wx ? 1 : from.x < wx ? -1 : g.xWall === "left" ? 1 : -1;
  const sy = from.y > wy ? 1 : from.y < wy ? -1 : g.yWall === "top" ? 1 : -1;
  return {
    x: clamp01(wx + sx * d.x * pxPerM / size.w),
    y: clamp01(wy + sy * d.y * pxPerM / size.h),
  };
}

/** The side wall a click picks in step 2: the nearer one. */
export function nearerSideWall(rect: WallRect, p: Frac): SideWall {
  return Math.abs(p.x - rect.x0) <= Math.abs(p.x - rect.x1) ? "left" : "right";
}

/** The top or bottom wall a click picks in step 3: the nearer one. */
export function nearerEndWall(rect: WallRect, p: Frac): EndWall {
  return Math.abs(p.y - rect.y0) <= Math.abs(p.y - rect.y1) ? "top" : "bottom";
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

/** What the drawing needs for one point: each wall's place, the dot on each
 *  (extended) wall that the guide starts from, whether the point is inside
 *  the rectangle, and the stretch each wall line is extended by to reach its
 *  dot (null when the dot is on the wall itself). */
export interface GuideGeometry {
  wallX: number;
  wallY: number;
  xDot: Frac;
  yDot: Frac;
  inside: boolean;
  xWallExtension: [number, number] | null;   // along the X wall, in y
  yWallExtension: [number, number] | null;   // along the Y wall, in x
}

export function guideGeometry(g: WallGuides, p: Frac): GuideGeometry {
  const wallX = xWallAt(g), wallY = yWallAt(g);
  const { x0, y0, x1, y1 } = g.rect;
  return {
    wallX,
    wallY,
    xDot: { x: wallX, y: p.y },
    yDot: { x: p.x, y: wallY },
    inside: insideRect(g.rect, p),
    xWallExtension: p.y < y0 ? [p.y, y0] : p.y > y1 ? [y1, p.y] : null,
    yWallExtension: p.x < x0 ? [p.x, x0] : p.x > x1 ? [x1, p.x] : null,
  };
}

/** The walls as saved: the rectangle in fractions and the two walls picked. */
export function serialiseWallGuides(g: WallGuides): string {
  return JSON.stringify({ v: 1, rect: g.rect, xWall: g.xWall, yWall: g.yWall });
}

/** Saved walls read back, or null for anything that isn't a valid save. */
export function parseWallGuides(raw: string | null | undefined): WallGuides | null {
  if (!raw) return null;
  let o: unknown;
  try {
    o = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!o || typeof o !== "object") return null;
  const { rect, xWall, yWall } = o as { rect?: unknown; xWall?: unknown; yWall?: unknown };
  if (!rect || typeof rect !== "object") return null;
  const { x0, y0, x1, y1 } = rect as Record<string, unknown>;
  const ok = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 1;
  if (!ok(x0) || !ok(y0) || !ok(x1) || !ok(y1) || !(x0 < x1) || !(y0 < y1)) return null;
  if (xWall !== "left" && xWall !== "right") return null;
  if (yWall !== "top" && yWall !== "bottom") return null;
  return { rect: { x0, y0, x1, y1 }, xWall, yWall };
}
