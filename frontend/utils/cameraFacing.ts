// Which way a camera faces on the floor plan (Prompt 143, D2): facing_deg is
// degrees clockwise from up, 0 to under 360, and fov_deg its field of view,
// 10-360 (90 when not given). The image's y grows downward, like the
// screen's, so up is -y: 0 points up, 90 right, 180 down, 270 left.
//
// Pure maths with no imports, so tools/harness/f143_wall_guides_check.ts can
// run it under Node as it is.

export const DEFAULT_FOV_DEG = 90;
export const MIN_FOV_DEG = 10;
export const MAX_FOV_DEG = 360;

/** Any angle as 0 <= deg < 360. */
export function normaliseFacing(deg: number): number {
  const d = ((deg % 360) + 360) % 360;
  return d >= 360 ? 0 : d + 0;   // a tiny negative can come back as 360; + 0 turns -0 into 0
}

/** The facing of a vector in the image's pixels (y down). */
export function facingFromVector(dx: number, dy: number): number {
  return normaliseFacing(Math.atan2(dx, -dy) * 180 / Math.PI);
}

/** The facing from a camera to a point, both fractions of the image, worked
 *  out in the image's pixels (size): x and y fractions have different scales
 *  unless the image is square. */
export function facingBetween(from: { x: number; y: number }, to: { x: number; y: number },
                              size: { w: number; h: number }): number {
  return facingFromVector((to.x - from.x) * size.w, (to.y - from.y) * size.h);
}

/** A unit vector for a facing, in pixels with y down. */
export function facingVector(deg: number): { x: number; y: number } {
  const r = deg * Math.PI / 180;
  return { x: Math.sin(r), y: -Math.cos(r) };
}

/** Whole degrees for the rotate handle. Normalised after rounding, so 359.6
 *  becomes 0, not 360 (which the backend refuses). */
export function roundFacing(deg: number): number {
  return normaliseFacing(Math.round(normaliseFacing(deg)));
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

/** The nearest of the 8 compass words, with up as N: 135 is "SE". */
export function compassWord(deg: number): string {
  return COMPASS[Math.round(normaliseFacing(deg) / 45) % 8];
}

/** Degrees as shown: whole ones without decimals, others with one. */
export function degreesText(deg: number): string {
  return Number.isInteger(deg) ? String(deg) : deg.toFixed(1);
}

/** "135° (SE)". */
export function facingLabel(deg: number): string {
  const n = normaliseFacing(deg);
  return `${degreesText(n)}° (${compassWord(n)})`;
}

/** The cone as an SVG path from (cx, cy), r long, centred on the facing and
 *  fov wide; a full circle for 360. */
export function conePath(cx: number, cy: number, r: number, facingDeg: number, fovDeg: number): string {
  if (fovDeg >= MAX_FOV_DEG) {
    return `M ${cx - r} ${cy} A ${r} ${r} 0 1 1 ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx - r} ${cy} Z`;
  }
  const a = facingVector(facingDeg - fovDeg / 2);
  const b = facingVector(facingDeg + fovDeg / 2);
  const large = fovDeg > 180 ? 1 : 0;
  // sweep-flag 1: clockwise on screen, the way the angles go
  return `M ${cx} ${cy} L ${cx + a.x * r} ${cy + a.y * r} A ${r} ${r} 0 ${large} 1 ${cx + b.x * r} ${cy + b.y * r} Z`;
}

export type Parsed = { ok: true; value: number | null } | { ok: false };

function parseDegrees(text: string): number | null | undefined {
  const t = text.trim();
  if (t === "") return null;
  if (!/^(\d+\.?\d*|\.\d+)$/.test(t)) return undefined;
  const v = Number(t);
  return Number.isFinite(v) ? v : undefined;
}

/** The dialog's Facing box: empty means not set (null); otherwise 0 to under 360. */
export function parseFacing(text: string): Parsed {
  const v = parseDegrees(text);
  if (v === undefined || (v !== null && !(v >= 0 && v < 360))) return { ok: false };
  return { ok: true, value: v };
}

/** The dialog's Field of view box: empty means the default (null); otherwise 10-360. */
export function parseFov(text: string): Parsed {
  const v = parseDegrees(text);
  if (v === undefined || (v !== null && !(v >= MIN_FOV_DEG && v <= MAX_FOV_DEG))) return { ok: false };
  return { ok: true, value: v };
}
