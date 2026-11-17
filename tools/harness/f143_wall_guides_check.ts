// Checks for Prompt 143's placement-guide maths, frontend/utils/wallGuides.ts (D1).
// Since 18 Nov the room is an outline with any number of corners; a rectangle here is
// an outline of 4 corners, with a side wall as X and the top or bottom wall as Y.
//
//   1  X and Y for each pair of walls (left/right with top/bottom)
//   2  a point outside the room: its distances, the guides' feet, the walls extended to them
//   3  point -> metres -> point round trips, inside and outside, every pair
//   4  typed X and Y give the right point: on each side of a wall, from a point on
//      the wall, clamped at the image's edge, and on the real floor's numbers
//   5  agreement with the backend's floor_service.derive_ap_metres()
//   6  the localStorage value: its key, a round trip, and old rectangle saves and bad
//      values read as none
//   7  Shift: a level or upright wall, chosen in pixels and lined up with the first
//      corner; the wall a click picks
//   8  metres shown to 2 decimal places; typed metres parsed
//   9  the pixel size used: the floor's stored size, else the image's natural size
//
// And for D2, the camera's direction (frontend/utils/cameraFacing.ts):
//  10  0 is up and angles go clockwise, with y growing downward: 90 right, 180 down
//  11  the angle from a camera to the cursor is worked out in pixels, not fractions
//  12  rounding for the handle wraps 359.6 to 0; compass words; the "135° (SE)" label
//  13  the cone's outline and the handle's tip point the right way; the dialog's boxes
//
// And for the walls' lengths (Herman, 18 Nov):
//  14  each wall's length in metres from the floor's px/m: a rectangle's sides, a slanted wall
//  15  a wall's length is the X or Y a device on the far wall reads, to the last bit
//
// And for the default cone of a camera with no facing saved (Herman, 18 Nov):
//  16  it points from the camera towards the middle of the map, in pixels, in whole degrees
//  17  a camera at the middle points straight up (0), not down
//  18  its first save sends the field of view it was drawn with (90); a saved one is kept
//
// And for walls at any slant (Herman, 18 Nov):
//  19  the distance to a slanted wall, square to it, and to its line past its end
//  20  point -> X and Y -> point round trips with slanted walls, both corner orders, and
//      typed distances read back as typed on the clicked point's side of each wall
//  21  a Y wall within 30 degrees of parallel to the X wall is refused, measured in pixels
//  22  a rectangle gives commit 11's results to the last bit: distances, typed points,
//      the guides' feet and extensions, and commit 9's lengths
//
// Run with Node, which strips the types itself (Node 23.6 or later; this PC has 24):
//   node tools/harness/f143_wall_guides_check.ts
// (from PowerShell on this PC: Node isn't on Git Bash's PATH). Exit 1 on a failure.
// It needs frontend/utils next to tools/, as in the repo or an export of both.
// No browser, no backend, nothing written.
import {
  canPairWalls, distanceToWallM, distancesM, footOnWall, formatMetres, guideGeometry, guideImageSize, insideOutline,
  nearestWall, parseMetres, parseWallGuides, placeAtDistances, serialiseWallGuides, sideOfWall, snapCorner,
  wallAngleDeg, wallGuidesKey, wallLengthM,
} from "../../frontend/utils/wallGuides.ts";
import type { Frac, ImageSize, WallGuides } from "../../frontend/utils/wallGuides.ts";
import {
  compassWord, conePath, defaultFacing, facingBetween, facingFromVector, facingLabel, facingSaveFields, facingVector,
  normaliseFacing, parseFacing, parseFov, roundFacing,
} from "../../frontend/utils/cameraFacing.ts";

const results: { check: number; name: string; ok: boolean }[] = [];

function check(num: number, name: string, ok: boolean, detail = ""): void {
  results.push({ check: num, name, ok });
  console.log(`[${ok ? "PASS" : "FAIL"}] #${num} ${name}${detail ? ` - ${detail}` : ""}`);
}

const near = (a: number, b: number, tol = 1e-9): boolean => Math.abs(a - b) <= tol;
const fmt = (p: Frac): string => `(${p.x.toFixed(4)}, ${p.y.toFixed(4)})`;

// The harness's test floor (tools/harness/harness_common.py): 1000 x 800 px at 50 px/m.
const HARNESS: ImageSize = { w: 1000, h: 800 };
const PPM = 50;
// The active floor's numbers on 17 Nov: 597 x 450 px at 46.08 px/m.
const REAL: ImageSize = { w: 597, h: 450 };
const REAL_PPM = 46.08;

// A rectangle as an outline: top, right, bottom and left walls (clockwise on screen), or the
// same corners the other way round. Its walls are found by side, whichever way it runs.
type SideWall = "left" | "right";
type EndWall = "top" | "bottom";
interface Rect { x0: number; y0: number; x1: number; y1: number }
const outlineOf = (r: Rect, reverse = false): Frac[] => {
  const c = [{ x: r.x0, y: r.y0 }, { x: r.x1, y: r.y0 }, { x: r.x1, y: r.y1 }, { x: r.x0, y: r.y1 }];
  return reverse ? c.reverse() : c;
};
const wallOf = (corners: Frac[], r: Rect, side: SideWall | EndWall): number => {
  for (let i = 0; i < corners.length; i++) {
    const a = corners[i], b = corners[(i + 1) % corners.length];
    if (side === "left" && a.x === r.x0 && b.x === r.x0) return i;
    if (side === "right" && a.x === r.x1 && b.x === r.x1) return i;
    if (side === "top" && a.y === r.y0 && b.y === r.y0) return i;
    if (side === "bottom" && a.y === r.y1 && b.y === r.y1) return i;
  }
  throw new Error(`no ${side} wall`);
};
const rectWalls = (r: Rect, xWall: SideWall, yWall: EndWall, reverse = false): WallGuides => {
  const corners = outlineOf(r, reverse);
  return { corners, xWall: wallOf(corners, r, xWall), yWall: wallOf(corners, r, yWall) };
};

// A room from 2 to 14 m across and 3.2 to 14.4 m down the harness floor.
const RECT: Rect = { x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.9 };
const PAIRS: [SideWall, EndWall][] = [["left", "top"], ["left", "bottom"], ["right", "top"], ["right", "bottom"]];
const walls = (xWall: SideWall, yWall: EndWall): WallGuides => rectWalls(RECT, xWall, yWall);
const segment = (s: [Frac, Frac] | null): string | null => (s ? JSON.stringify(s.map((p) => [p.x, p.y]).sort()) : null);

// 1. P = (0.3, 0.4): 4 m from the left wall, 8 m from the right; 3.2 m from the top, 8 m from the bottom.
{
  const P = { x: 0.3, y: 0.4 };
  const want: Record<string, [number, number]> = {
    "left/top": [4, 3.2], "left/bottom": [4, 8], "right/top": [8, 3.2], "right/bottom": [8, 8],
  };
  const got = PAIRS.map(([xw, yw]) => {
    const d = distancesM(walls(xw, yw), P, HARNESS, PPM);
    const [wx, wy] = want[`${xw}/${yw}`];
    return { pair: `${xw}/${yw}`, d, ok: near(d.x, wx) && near(d.y, wy) };
  });
  check(1, "X and Y for each pair of walls", got.every((g) => g.ok),
    got.map((g) => `${g.pair} X ${formatMetres(g.d.x)} Y ${formatMetres(g.d.y)}`).join("; "));
}

// 2. Q = (0.05, 0.95), left of the room and below it.
{
  const Q = { x: 0.05, y: 0.95 };
  const lt = distancesM(walls("left", "top"), Q, HARNESS, PPM);
  const rb = distancesM(walls("right", "bottom"), Q, HARNESS, PPM);
  const g = guideGeometry(walls("left", "top"), Q, HARNESS);
  const inside = guideGeometry(walls("left", "top"), { x: 0.3, y: 0.4 }, HARNESS);
  const ok = near(lt.x, 1) && near(lt.y, 12) && near(rb.x, 13) && near(rb.y, 0.8)
    && !insideOutline(walls("left", "top").corners, Q) && !g.inside
    && g.x.foot.x === 0.1 && g.x.foot.y === 0.95 && g.y.foot.x === 0.05 && g.y.foot.y === 0.2
    && segment(g.x.extension) === segment([{ x: 0.1, y: 0.9 }, { x: 0.1, y: 0.95 }])
    && segment(g.y.extension) === segment([{ x: 0.1, y: 0.2 }, { x: 0.05, y: 0.2 }])
    && inside.inside && inside.x.extension === null && inside.y.extension === null;
  check(2, "a point outside the room: its distances, the guides' feet, and the walls extended to them", ok,
    `left/top X ${formatMetres(lt.x)} Y ${formatMetres(lt.y)}; right/bottom X ${formatMetres(rb.x)} Y ${formatMetres(rb.y)}; `
    + `extensions ${segment(g.x.extension)} ${segment(g.y.extension)}`);
}

// 3. Round trips over a grid that reaches outside the room on every side.
{
  let worst = 0, n = 0;
  for (const [xw, yw] of PAIRS) {
    const g = walls(xw, yw);
    for (let i = 0; i <= 20; i++) {
      for (let j = 0; j <= 20; j++) {
        const p = { x: i / 20, y: j / 20 };
        const back = placeAtDistances(g, p, p, distancesM(g, p, HARNESS, PPM), HARNESS, PPM);
        worst = Math.max(worst, Math.abs(back.x - p.x), Math.abs(back.y - p.y));
        n++;
      }
    }
  }
  check(3, "point -> metres -> point round trips (inside and outside, every pair of walls)",
    worst < 1e-12, `${n} points, worst error ${worst.toExponential(2)} of the image`);
}

// 4. Typed distances.
{
  const lt = walls("left", "top"), rb = walls("right", "bottom");
  const at = (g: WallGuides, from: Frac, x: number, y: number) => placeAtDistances(g, from, from, { x, y }, HARNESS, PPM);
  const cases: { name: string; got: Frac; want: Frac }[] = [
    { name: "inside, left/top", got: at(lt, { x: 0.3, y: 0.4 }, 2, 3), want: { x: 0.2, y: 0.3875 } },
    { name: "inside, right/bottom", got: at(rb, { x: 0.3, y: 0.4 }, 2, 3), want: { x: 0.6, y: 0.7125 } },
    { name: "clicked left of the left wall", got: at(lt, { x: 0.05, y: 0.4 }, 1.5, 3), want: { x: 0.025, y: 0.3875 } },
    { name: "clicked above the top wall", got: at(lt, { x: 0.3, y: 0.1 }, 2, 0.8), want: { x: 0.2, y: 0.15 } },
    { name: "clicked on the walls: into the room", got: at(lt, { x: 0.1, y: 0.2 }, 2, 3), want: { x: 0.2, y: 0.3875 } },
    { name: "on the right/bottom walls: into the room", got: at(rb, { x: 0.7, y: 0.9 }, 2, 3), want: { x: 0.6, y: 0.7125 } },
    { name: "past the image's edge: clamped", got: at(lt, { x: 0.3, y: 0.4 }, 50, 50), want: { x: 1, y: 1 } },
  ];
  const bad = cases.filter((c) => !near(c.got.x, c.want.x) || !near(c.got.y, c.want.y));
  // As the guide itself reads them: typed 2.00 and 3.00 read back as 2.00 and 3.00.
  const readsHarness = distancesM(lt, cases[0].got, HARNESS, PPM);
  const realWalls = rectWalls({ x0: 0.12, y0: 0.08, x1: 0.83, y1: 0.91 }, "left", "top");
  const realPoint = placeAtDistances(realWalls, { x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }, { x: 2, y: 3 }, REAL, REAL_PPM);
  const readsReal = distancesM(realWalls, realPoint, REAL, REAL_PPM);
  const clampedReads = distancesM(lt, cases[6].got, HARNESS, PPM);
  // Only X typed: Y keeps the point's coordinate exactly, as before.
  const onlyX = placeAtDistances(lt, { x: 0.3, y: 0.4 }, { x: 0.3, y: 0.4 }, { x: 2, y: null }, HARNESS, PPM);
  check(4, "typed X and Y give the right point, read back by the guide as typed (well within 1 cm)",
    bad.length === 0 && near(readsHarness.x, 2) && near(readsHarness.y, 3) && near(readsReal.x, 2) && near(readsReal.y, 3)
      && near(clampedReads.x, 18) && near(clampedReads.y, 12.8) && onlyX.x === 0.2 && onlyX.y === 0.4,
    (bad.length ? `wrong: ${bad.map((c) => `${c.name} ${fmt(c.got)} not ${fmt(c.want)}`).join("; ")}; ` : "")
    + `reads ${formatMetres(readsHarness.x)}/${formatMetres(readsHarness.y)} (harness), `
    + `${formatMetres(readsReal.x)}/${formatMetres(readsReal.y)} (597x450 floor); clamped reads ${formatMetres(clampedReads.x)}/${formatMetres(clampedReads.y)}`);
}

// 5. floor_service.derive_ap_metres() measures from the image's top left corner. These
// numbers came from running it (on the harness fakes, the 17 Nov build of 143) for the
// harness floor and for a floor with the active floor's numbers; walls on the image's
// left and top edges must read the same.
{
  const REF = [
    { size: HARNESS, ppm: PPM, x: 0.1, y: 0.125, x_m: 2.0, y_m: 2.0 },
    { size: HARNESS, ppm: PPM, x: 0.7, y: 0.125, x_m: 14.0, y_m: 2.0 },
    { size: HARNESS, ppm: PPM, x: 0.4, y: 0.75, x_m: 8.0, y_m: 12.0 },
    { size: HARNESS, ppm: PPM, x: 0.3337, y: 0.6421, x_m: 6.6739999999999995, y_m: 10.273599999999998 },
    { size: HARNESS, ppm: PPM, x: 1.0, y: 1.0, x_m: 20.0, y_m: 16.0 },
    { size: HARNESS, ppm: PPM, x: 0.0, y: 0.0, x_m: 0.0, y_m: 0.0 },
    { size: REAL, ppm: REAL_PPM, x: 0.25, y: 0.5, x_m: 3.238932291666667, y_m: 4.8828125 },
    { size: REAL, ppm: REAL_PPM, x: 0.4891, y: 0.2633, x_m: 6.336647135416667, y_m: 2.5712890624999996 },
    { size: REAL, ppm: REAL_PPM, x: 1.0, y: 1.0, x_m: 12.955729166666668, y_m: 9.765625 },
    { size: REAL, ppm: REAL_PPM, x: 0.123, y: 0.987, x_m: 1.5935546875, y_m: 9.638671875 },
  ];
  const corner = rectWalls({ x0: 0, y0: 0, x1: 1, y1: 1 }, "left", "top");
  let worst = 0, exact = 0;
  for (const r of REF) {
    const d = distancesM(corner, { x: r.x, y: r.y }, r.size, r.ppm);
    worst = Math.max(worst, Math.abs(d.x - r.x_m), Math.abs(d.y - r.y_m));
    if (d.x === r.x_m && d.y === r.y_m) exact++;
  }
  check(5, "agrees with derive_ap_metres() for the harness floor and the 597 x 450 floor", worst <= 1e-12,
    `${REF.length} points, ${exact} identical to the last bit, worst difference ${worst.toExponential(2)} m`);
}

// 6. What's kept in localStorage.
{
  const g = walls("right", "top");
  const back = parseWallGuides(serialiseWallGuides(g));
  const v2 = (o: object) => JSON.stringify({ v: 2, corners: g.corners, xWall: g.xWall, yWall: g.yWall, ...o });
  const bad = ["", "not json", "null", "[]", "{}", "42",
    // the rectangle saves of before 18 Nov (v 1) read as no walls: they're drawn again
    JSON.stringify({ v: 1, rect: { x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.9 }, xWall: "left", yWall: "top" }),
    JSON.stringify({ rect: { x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.9 }, xWall: "left", yWall: "top" }),
    v2({ v: 3 }), v2({ corners: g.corners.slice(0, 2) }), v2({ corners: [...g.corners.slice(0, 3), { x: 1.2, y: 0.5 }] }),
    v2({ corners: [...g.corners.slice(0, 3), { x: "0.5", y: 0.5 }] }), v2({ corners: [...g.corners.slice(0, 3), null] }),
    v2({ xWall: g.yWall }), v2({ yWall: 4 }), v2({ xWall: 0.5 }), v2({ yWall: undefined }), v2({ xWall: -1 }),
    v2({ corners: [g.corners[0], g.corners[0], g.corners[2], g.corners[3]], xWall: 0, yWall: 1 }),   // an X wall with no length
  ];
  const accepted = bad.filter((s) => parseWallGuides(s) !== null);
  check(6, "localStorage: the key, a round trip, and old rectangle saves and bad values read as no walls",
    wallGuidesKey("355d6a73-floor") === "skye-wall-guides:355d6a73-floor" && parseWallGuides(null) === null
      && JSON.stringify(back) === JSON.stringify(g) && accepted.length === 0,
    `round trip ${JSON.stringify(back) === JSON.stringify(g)}; ${bad.length - accepted.length} of ${bad.length} bad or old values refused`);
}

// 7. Shift while drawing, and the wall a click picks.
{
  const tol = { x: 0.01, y: 0.01 };
  const level = snapCorner({ x: 0.2, y: 0.2 }, { x: 0.5, y: 0.23 }, HARNESS, null, tol);
  const upright = snapCorner({ x: 0.5, y: 0.2 }, { x: 0.52, y: 0.6 }, HARNESS, null, tol);
  // Closing a rectangle: the fourth corner lines up with the first, so the last wall is upright.
  const closing = snapCorner({ x: 0.5, y: 0.6 }, { x: 0.205, y: 0.62 }, HARNESS, { x: 0.2, y: 0.2 }, tol);
  // In pixels: 0.1 across and 0.12 down on 1000 x 800 is 100 px by 96 px, so level, though fractions say upright.
  const pixels = snapCorner({ x: 0, y: 0 }, { x: 0.1, y: 0.12 }, HARNESS, null, tol);
  const room: Frac[] = [{ x: 0.1, y: 0.2 }, { x: 0.7, y: 0.2 }, { x: 0.8, y: 0.9 }, { x: 0.1, y: 0.9 }];
  const withDot: Frac[] = [{ x: 0.1, y: 0.2 }, { x: 0.7, y: 0.2 }, { x: 0.7, y: 0.2 }, { x: 0.8, y: 0.9 }, { x: 0.1, y: 0.9 }];
  const picks = [
    nearestWall(room, { x: 0.4, y: 0.18 }, HARNESS), nearestWall(room, { x: 0.77, y: 0.55 }, HARNESS),
    nearestWall(room, { x: 0.5, y: 0.95 }, HARNESS), nearestWall(room, { x: 0.05, y: 0.5 }, HARNESS),
    nearestWall(withDot, { x: 0.71, y: 0.19 }, HARNESS),
  ];
  const ok = level.x === 0.5 && level.y === 0.2 && upright.x === 0.5 && upright.y === 0.6
    && closing.x === 0.2 && closing.y === 0.6 && pixels.x === 0.1 && pixels.y === 0
    && JSON.stringify(picks) === JSON.stringify([0, 1, 2, 3, 0]);
  check(7, "Shift makes a wall level or upright (chosen in pixels) and lines the last corner up with the first; a click picks the nearest wall", ok,
    `level ${fmt(level)} upright ${fmt(upright)} closing ${fmt(closing)} pixels ${fmt(pixels)}; picks ${JSON.stringify(picks)}`);
}

// 8. What the labels show, and what the X and Y boxes accept.
{
  const shown = [formatMetres(3.2), formatMetres(4.5), formatMetres(0), formatMetres(12.345678)];
  const parsed = ["2", "2.", " 2.50 ", ".5", "12.25"].map(parseMetres);
  const refused = ["-1", "1e3", "", "abc", "2.5.1", "2,5"].map(parseMetres);
  check(8, "metres shown to 2 decimal places; typed metres parsed, other text refused",
    JSON.stringify(shown) === JSON.stringify(["3.20", "4.50", "0.00", "12.35"])
      && JSON.stringify(parsed) === JSON.stringify([2, 2, 2.5, 0.5, 12.25]) && refused.every((v) => v === null),
    `shown ${shown.join(", ")}; parsed ${JSON.stringify(parsed)}`);
}

// 9. The pixel size the metres are counted in.
{
  const stored = guideImageSize({ image_width_px: 597, image_height_px: 450 }, { w: 1194, h: 900 });
  const fallback = guideImageSize({ image_width_px: null, image_height_px: 450 }, { w: 1194, h: 900 });
  const zero = guideImageSize({ image_width_px: 0, image_height_px: 0 }, { w: 640, h: 480 });
  const none = guideImageSize({}, null);
  check(9, "the floor's image_width_px and image_height_px when both are set, else the natural size",
    JSON.stringify(stored) === JSON.stringify({ w: 597, h: 450 }) && JSON.stringify(fallback) === JSON.stringify({ w: 1194, h: 900 })
      && JSON.stringify(zero) === JSON.stringify({ w: 640, h: 480 }) && none === null,
    `stored ${JSON.stringify(stored)} fallback ${JSON.stringify(fallback)}`);
}

// 10. The convention, in the image's pixels with y growing downward.
{
  const dirs: [string, number, number, number][] = [
    ["up", 0, -1, 0], ["right", 1, 0, 90], ["down", 0, 1, 180], ["left", -1, 0, 270],
    ["down-right", 1, 1, 135], ["up-left", -1, -1, 315], ["up-right", 1, -1, 45], ["down-left", -1, 1, 225],
  ];
  const wrong = dirs.filter(([, dx, dy, deg]) => !near(facingFromVector(dx, dy), deg));
  check(10, "0 is up and angles go clockwise (y down): right 90, down 180, left 270", wrong.length === 0,
    dirs.map(([n, dx, dy]) => `${n} ${facingFromVector(dx, dy).toFixed(1)}`).join(", "));
}

// 11. From a camera to the cursor on the 597 x 450 floor: 0.1 across and 0.1 down is
// 59.7 px right and 45 px down, so about 127°, not the 135° that fractions would give.
{
  const got = facingBetween({ x: 0.5, y: 0.5 }, { x: 0.6, y: 0.6 }, REAL);
  const want = 180 - Math.atan(59.7 / 45) * 180 / Math.PI;
  const square = facingBetween({ x: 0.5, y: 0.5 }, { x: 0.6, y: 0.6 }, { w: 500, h: 500 });
  check(11, "the camera-to-cursor angle is worked out in the image's pixels", near(got, want, 1e-9) && near(square, 135, 1e-9)
    && !near(got, 135, 1), `597 x 450: ${got.toFixed(2)}° (want ${want.toFixed(2)}°); square image: ${square.toFixed(2)}°`);
}

// 12. Rounding, compass words and the label.
{
  const rounded = [359.6, -0.4, 359.4, 720.2, 89.5, -90].map(roundFacing);
  const words = [0, 22.4, 22.5, 45, 90, 135, 180, 225, 270, 315, 337.4, 337.5, 359].map(compassWord);
  const ok = JSON.stringify(rounded) === JSON.stringify([0, 0, 359, 0, 90, 270])
    && JSON.stringify(words) === JSON.stringify(["N", "N", "NE", "NE", "E", "SE", "S", "SW", "W", "NW", "NW", "N", "N"])
    && facingLabel(135) === "135° (SE)" && facingLabel(90.5) === "90.5° (E)" && facingLabel(0) === "0° (N)"
    && normaliseFacing(-0) === 0 && Object.is(normaliseFacing(-0), 0) && normaliseFacing(360) === 0;
  check(12, "the handle's whole degrees wrap 359.6 to 0 (never 360); compass words; \"135° (SE)\"", ok,
    `rounded ${JSON.stringify(rounded)}; words ${words.join(" ")}; label ${facingLabel(135)}`);
}

// 13. The cone and the handle as drawn, and the dialog's Facing and Field of view boxes.
{
  const right = facingVector(90), down = facingVector(180);
  const path = conePath(100, 100, 78, 90, 90);
  // Facing right with 90°: from the centre to 45° and round to 135°, both on the right-hand side.
  const nums = (path.match(/-?\d+(\.\d+)?(e-?\d+)?/g) ?? []).map(Number);
  const [mx, my, lx, ly] = nums;
  const ex = nums[nums.length - 2], ey = nums[nums.length - 1];
  const full = conePath(100, 100, 78, 0, 360);
  const facings = ["", "0", "90", "359.9", "360", "-1", "abc", "45.5"].map((t) => {
    const p = parseFacing(t);
    return p.ok ? p.value : "bad";
  });
  const fovs = ["", "10", "360", "9", "361", "120"].map((t) => {
    const p = parseFov(t);
    return p.ok ? p.value : "bad";
  });
  const ok = near(right.x, 1) && near(right.y, 0) && near(down.x, 0) && near(down.y, 1)
    && mx === 100 && my === 100 && lx > 100 && ly < 100 && ex > 100 && ey > 100 && path.includes(" 0 0 1 ")
    && full.split(" A ").length === 3 && conePath(0, 0, 1, 0, 270).includes(" 0 1 1 ")
    && JSON.stringify(facings) === JSON.stringify([null, 0, 90, 359.9, "bad", "bad", "bad", 45.5])
    && JSON.stringify(fovs) === JSON.stringify([null, 10, 360, "bad", "bad", 120]);
  check(13, "a cone facing 90° opens to the right, the handle at 90° is right and at 180° down; the dialog's boxes", ok,
    `start (${lx.toFixed(1)}, ${ly.toFixed(1)}) end (${ex.toFixed(1)}, ${ey.toFixed(1)}); facings ${JSON.stringify(facings)}; fovs ${JSON.stringify(fovs)}`);
}

// The walls' lengths (Herman, 18 Nov): a room on the 597 x 450 floor, and the two floors.
const REAL_ROOM: Rect = { x0: 0.12, y0: 0.08, x1: 0.83, y1: 0.91 };
const FLOORS: { name: string; size: ImageSize; ppm: number; rect: Rect }[] = [
  { name: "harness", size: HARNESS, ppm: PPM, rect: RECT },
  { name: "597 x 450", size: REAL, ppm: REAL_PPM, rect: REAL_ROOM },
];

// 14. A wall's length in metres. RECT is 12 m by 11.2 m on the harness floor; REAL_ROOM is
// 0.71 x 597 ÷ 46.08 by 0.83 x 450 ÷ 46.08; a slanted wall 300 px across and 320 px down is
// hypot(300, 320) ÷ 50 m.
{
  const top = wallLengthM({ x: 0.1, y: 0.2 }, { x: 0.7, y: 0.2 }, HARNESS, PPM);
  const left = wallLengthM({ x: 0.1, y: 0.9 }, { x: 0.1, y: 0.2 }, HARNESS, PPM);
  const realW = wallLengthM({ x: 0.83, y: 0.08 }, { x: 0.12, y: 0.08 }, REAL, REAL_PPM);
  const realH = wallLengthM({ x: 0.12, y: 0.08 }, { x: 0.12, y: 0.91 }, REAL, REAL_PPM);
  const slanted = wallLengthM({ x: 0.1, y: 0.2 }, { x: 0.4, y: 0.6 }, HARNESS, PPM);
  const ok = near(top, 12) && near(left, 11.2) && near(realW, 9.198567708333333) && near(realH, 8.10546875)
    && formatMetres(realW) === "9.20" && formatMetres(realH) === "8.11" && near(slanted, Math.hypot(300, 320) / 50);
  check(14, "each wall's length in metres from the floor's px/m: a rectangle's sides, and a slanted wall", ok,
    `harness ${formatMetres(top)} x ${formatMetres(left)} m; 597 x 450 room ${formatMetres(realW)} x ${formatMetres(realH)} m; `
    + `slanted ${formatMetres(slanted)} m`);
}

// 15. The lengths and the guides agree to the last bit: on the far side wall a device reads
// X = the end walls' length, and on the far end wall Y = the side walls', whichever walls are picked.
{
  const cases: { name: string; got: number; want: number }[] = [];
  for (const f of FLOORS) {
    const r = f.rect, mid = { x: (r.x0 + r.x1) / 2, y: (r.y0 + r.y1) / 2 };
    const width = wallLengthM({ x: r.x0, y: r.y0 }, { x: r.x1, y: r.y0 }, f.size, f.ppm);
    const height = wallLengthM({ x: r.x0, y: r.y0 }, { x: r.x0, y: r.y1 }, f.size, f.ppm);
    const d = (xw: SideWall, yw: EndWall, p: Frac) => distancesM(rectWalls(r, xw, yw), p, f.size, f.ppm);
    cases.push(
      { name: `${f.name}, X from the left wall at the right wall`, got: d("left", "top", { x: r.x1, y: mid.y }).x, want: width },
      { name: `${f.name}, X from the right wall at the left wall`, got: d("right", "top", { x: r.x0, y: mid.y }).x, want: width },
      { name: `${f.name}, Y from the top wall at the bottom wall`, got: d("left", "top", { x: mid.x, y: r.y1 }).y, want: height },
      { name: `${f.name}, Y from the bottom wall at the top wall`, got: d("left", "bottom", { x: mid.x, y: r.y0 }).y, want: height },
    );
  }
  const bad = cases.filter((c) => c.got !== c.want);
  check(15, "a wall's length is the X or Y a device on the far wall reads (identical)",
    bad.length === 0, bad.length ? `differ: ${bad.map((c) => c.name).join("; ")}` : `${cases.length} of ${cases.length} identical`);
}

// 16. Towards the middle from each side of the harness floor (1000 x 800), and from two
// corners of the 597 x 450 floor. From the top left corner the middle is 500 px right and
// 400 px down on the harness floor, about 128.66°, so 129; on the 597 x 450 floor 298.5 px
// right and 225 px down, about 127.01°, so 127 (135° in fractions on both).
{
  const cases: [string, Frac, ImageSize, number][] = [
    ["left of the middle", { x: 0.25, y: 0.5 }, HARNESS, 90],
    ["above it", { x: 0.5, y: 0.1 }, HARNESS, 180],
    ["right of it", { x: 0.9, y: 0.5 }, HARNESS, 270],
    ["below it", { x: 0.5, y: 0.95 }, HARNESS, 0],
    ["top left, 1000 x 800", { x: 0, y: 0 }, HARNESS, 129],
    ["top left, 597 x 450", { x: 0, y: 0 }, REAL, 127],
    ["bottom right, 597 x 450", { x: 1, y: 1 }, REAL, 307],
  ];
  const got = cases.map(([name, cam, size, want]) => ({ name, got: defaultFacing(cam, size), want }));
  const bad = got.filter((g) => g.got !== g.want || !Number.isInteger(g.got));
  check(16, "a camera with no facing points at the middle of the map, in the image's pixels, in whole degrees", bad.length === 0,
    got.map((g) => `${g.name} ${g.got}`).join("; "));
}

// 17. At the middle there is no direction, so straight up; facingBetween() alone gives 180
// there (atan2(0, -0)). Within half an image pixel counts as the middle; a pixel off doesn't.
{
  const atMiddle = defaultFacing({ x: 0.5, y: 0.5 }, REAL);
  const raw = facingBetween({ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }, REAL);
  const nearly = defaultFacing({ x: 0.5 + 0.3 / 597, y: 0.5 - 0.3 / 450 }, REAL);   // 0.3 px right and 0.3 px up: 0.42 px away
  const pixelLeft = defaultFacing({ x: 0.5 - 1 / 597, y: 0.5 }, REAL);             // 1 px left of the middle: points right
  check(17, "a camera at the middle points straight up (0), not down; under half a pixel away counts as the middle",
    Object.is(atMiddle, 0) && raw === 180 && nearly === 0 && pixelLeft === 90,
    `at the middle ${atMiddle} (facingBetween alone ${raw}); 0.42 px away ${nearly}; 1 px left ${pixelLeft}`);
}

// 18. What saving sends: with no field of view saved, the facing and the 90 the default cone
// was drawn with; with one saved, the facing alone, so the backend keeps it.
{
  const first = facingSaveFields(null, 134);
  const older = facingSaveFields(undefined, 0);
  const kept = facingSaveFields(60, 200);
  check(18, "a first facing is saved with the field of view it was drawn with (90); a saved field of view is kept",
    JSON.stringify(first) === JSON.stringify({ facing_deg: 134, fov_deg: 90 })
      && JSON.stringify(older) === JSON.stringify({ facing_deg: 0, fov_deg: 90 })
      && JSON.stringify(kept) === JSON.stringify({ facing_deg: 200 }) && !("fov_deg" in kept),
    `none saved ${JSON.stringify(first)}; 60 saved ${JSON.stringify(kept)}`);
}

// Walls at any slant (Herman, 18 Nov). A room with one slanted wall (right), and a five-cornered
// one with two (right and bottom right), both clockwise on screen.
const SLANT: Frac[] = [{ x: 0.1, y: 0.2 }, { x: 0.7, y: 0.2 }, { x: 0.8, y: 0.9 }, { x: 0.1, y: 0.9 }];
const FIVE: Frac[] = [{ x: 0.15, y: 0.15 }, { x: 0.6, y: 0.1 }, { x: 0.85, y: 0.45 }, { x: 0.55, y: 0.85 }, { x: 0.1, y: 0.8 }];

// 19. A wall from the image's top left corner to its bottom right on the harness floor runs
// (0, 0) -> (1000, 800) px. The point (0.5, 0.25) is (500, 200) px, so |1000 x 200 - 800 x 500|
// ÷ hypot(1000, 800) ≈ 156.17 px ≈ 3.12 m from it, and its foot is at 0.4024 along the wall.
// Past a wall's end, the distance is to its line extended, and the guide extends the wall.
{
  const a = { x: 0, y: 0 }, b = { x: 1, y: 1 }, p = { x: 0.5, y: 0.25 };
  const d = distanceToWallM(a, b, p, HARNESS, PPM);
  const want = Math.abs(1000 * 200 - 800 * 500) / Math.hypot(1000, 800) / PPM;
  const { foot, t } = footOnWall(a, b, p, HARNESS);
  const wantT = (500 * 1000 + 200 * 800) / (1000 * 1000 + 800 * 800);
  // A short wall from (0.2, 0.2) to (0.4, 0.3), and a point beyond its far end: to the line, not the end.
  const shortA = { x: 0.2, y: 0.2 }, shortB = { x: 0.4, y: 0.3 }, beyond = { x: 0.8, y: 0.3 };
  const dBeyond = distanceToWallM(shortA, shortB, beyond, HARNESS, PPM);
  const wantBeyond = Math.abs(200 * 80 - 80 * 600) / Math.hypot(200, 80) / PPM;   // wall (200, 80) px; point (600, 80) px from its start
  const toEnd = Math.hypot((beyond.x - shortB.x) * 1000, (beyond.y - shortB.y) * 800) / PPM;
  const g = guideGeometry({ corners: [shortA, shortB, { x: 0.3, y: 0.7 }], xWall: 0, yWall: 1 }, beyond, HARNESS);
  const ok = near(d, want) && near(t, wantT) && near(foot.x, wantT) && near(foot.y, wantT)
    && near(dBeyond, wantBeyond) && !near(dBeyond, toEnd, 1e-6) && g.x.extension !== null
    && g.x.extension[0] === shortB && near(g.x.extension[1].x, g.x.foot.x);
  check(19, "the distance to a slanted wall is square to it, and past its end is to its line extended", ok,
    `diagonal ${formatMetres(d)} m (want ${formatMetres(want)}), foot at ${t.toFixed(4)} along; past the end `
    + `${formatMetres(dBeyond)} m to the line (${formatMetres(toEnd)} m to the end)`);
}

// 20. Round trips with slanted walls: X and Y for each point of a grid reaching outside the
// room, then the point back from them, for several pairs of walls and both corner orders. And
// typed distances from a clicked point read back as typed, on that point's side of each wall.
{
  const sets: { name: string; corners: Frac[]; x: number; y: number }[] = [
    { name: "slanted X, top Y", corners: SLANT, x: 1, y: 0 },
    { name: "top X, slanted Y", corners: SLANT, x: 0, y: 1 },
    { name: "slanted X, bottom Y", corners: SLANT, x: 1, y: 2 },
    { name: "two slanted walls", corners: FIVE, x: 1, y: 2 },
    { name: "two slanted walls, X and Y swapped", corners: FIVE, x: 2, y: 1 },
  ];
  let worst = 0, n = 0, typedWorst = 0, sideMismatch = 0;
  for (const s of sets) {
    for (const reverse of [false, true]) {
      const corners = reverse ? [...s.corners].reverse() : s.corners;
      const k = corners.length;
      // Reversing the corners turns wall i (corner i to i+1) into wall k-2-i.
      const g: WallGuides = reverse ? { corners, xWall: (2 * k - 2 - s.x) % k, yWall: (2 * k - 2 - s.y) % k } : { corners, xWall: s.x, yWall: s.y };
      for (let i = 0; i <= 20; i++) {
        for (let j = 0; j <= 20; j++) {
          const p = { x: i / 20, y: j / 20 };
          const back = placeAtDistances(g, p, p, distancesM(g, p, HARNESS, PPM), HARNESS, PPM);
          if (back.x > 0 && back.x < 1 && back.y > 0 && back.y < 1) {
            worst = Math.max(worst, Math.abs(back.x - p.x), Math.abs(back.y - p.y));
            n++;
          }
          const typed = placeAtDistances(g, p, p, { x: 1.5, y: 2.5 }, HARNESS, PPM);
          if (typed.x > 0 && typed.x < 1 && typed.y > 0 && typed.y < 1) {
            const reads = distancesM(g, typed, HARNESS, PPM);
            typedWorst = Math.max(typedWorst, Math.abs(reads.x - 1.5), Math.abs(reads.y - 2.5));
            const sx = sideOfWall(corners, g.xWall, p, HARNESS) || 1, sy = sideOfWall(corners, g.yWall, p, HARNESS) || 1;
            if (sideOfWall(corners, g.xWall, typed, HARNESS) !== sx || sideOfWall(corners, g.yWall, typed, HARNESS) !== sy) sideMismatch++;
          }
        }
      }
    }
  }
  check(20, "with slanted walls, point -> X and Y -> point round trips, and typed distances read back as typed on the clicked side",
    worst < 1e-9 && typedWorst < 1e-9 && sideMismatch === 0,
    `${n} points, worst ${worst.toExponential(2)} of the image; typed reads off by at most ${typedWorst.toExponential(2)} m; `
    + `${sideMismatch} on the wrong side`);
}

// 21. The Y wall must be more than 30° from parallel to the X wall, measured in the image's
// pixels. Wall 0 is level; wall 1 leaves its end at the given angle (in pixels) above level.
{
  const at = (deg: number): Frac[] => {
    const r = deg * Math.PI / 180;
    const s = { x: 0.5, y: 0.5 }, e = { x: 0.5 + 200 * Math.cos(r) / 1000, y: 0.5 - 200 * Math.sin(r) / 800 };
    return [{ x: 0.1, y: 0.5 }, s, e, { x: 0.1, y: 0.2 }];
  };
  const angles = [0, 20, 29, 30, 31, 45, 90];
  const allowed = angles.map((deg) => canPairWalls(at(deg), 0, 1, HARNESS));
  const measured = angles.map((deg) => wallAngleDeg(at(deg), 0, 1, HARNESS));
  // 33° in fractions is about 27.5° in pixels on a 1000 x 800 image: refused.
  const r33 = 33 * Math.PI / 180;
  const fracs: Frac[] = [{ x: 0.1, y: 0.5 }, { x: 0.5, y: 0.5 }, { x: 0.5 + 0.2 * Math.cos(r33), y: 0.5 - 0.2 * Math.sin(r33) }, { x: 0.1, y: 0.2 }];
  const sameWall = canPairWalls(SLANT, 1, 1, HARNESS);
  const ok = JSON.stringify(allowed) === JSON.stringify([false, false, false, false, true, true, true])
    && measured.every((m, i) => near(m, angles[i], 1e-9)) && !canPairWalls(fracs, 0, 1, HARNESS)
    && near(wallAngleDeg(fracs, 0, 1, HARNESS), Math.atan(0.8 * Math.tan(r33)) * 180 / Math.PI, 1e-9) && !sameWall;
  check(21, "a Y wall within 30° of parallel to the X wall is refused (30° itself too), measured in pixels", ok,
    angles.map((deg, i) => `${deg}° ${allowed[i] ? "ok" : "refused"}`).join(", ")
    + `; 33° in fractions is ${wallAngleDeg(fracs, 0, 1, HARNESS).toFixed(2)}° in pixels`);
}

// 22. A rectangle gives commit 11's results to the last bit. Commit 11's rectangle maths,
// as it was (frontend/utils/wallGuides.ts at e0d5fec), is copied here as the reference.
{
  const clamp = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
  const old = {
    distancesM: (r: Rect, xw: SideWall, yw: EndWall, p: Frac, size: ImageSize, ppm: number) => ({
      x: Math.abs(p.x - (xw === "left" ? r.x0 : r.x1)) * size.w / ppm,
      y: Math.abs(p.y - (yw === "top" ? r.y0 : r.y1)) * size.h / ppm,
    }),
    pointAtDistances: (r: Rect, xw: SideWall, yw: EndWall, from: Frac, d: { x: number; y: number }, size: ImageSize, ppm: number) => {
      const wx = xw === "left" ? r.x0 : r.x1, wy = yw === "top" ? r.y0 : r.y1;
      const sx = from.x > wx ? 1 : from.x < wx ? -1 : xw === "left" ? 1 : -1;
      const sy = from.y > wy ? 1 : from.y < wy ? -1 : yw === "top" ? 1 : -1;
      return { x: clamp(wx + sx * d.x * ppm / size.w), y: clamp(wy + sy * d.y * ppm / size.h) };
    },
    guide: (r: Rect, xw: SideWall, yw: EndWall, p: Frac) => {
      const wallX = xw === "left" ? r.x0 : r.x1, wallY = yw === "top" ? r.y0 : r.y1;
      return {
        xDot: { x: wallX, y: p.y }, yDot: { x: p.x, y: wallY },
        xExt: p.y < r.y0 ? [p.y, r.y0] : p.y > r.y1 ? [r.y1, p.y] : null,
        yExt: p.x < r.x0 ? [p.x, r.x0] : p.x > r.x1 ? [r.x1, p.x] : null,
      };
    },
    rectSizeM: (r: Rect, size: ImageSize, ppm: number) => ({ w: (r.x1 - r.x0) * size.w / ppm, h: (r.y1 - r.y0) * size.h / ppm }),
  };
  const span = (s: [Frac, Frac] | null, axis: "x" | "y"): string | null => (s ? JSON.stringify([s[0][axis], s[1][axis]].sort()) : null);
  let cases = 0, differ = 0;
  const firstDiff: string[] = [];
  const same = (name: string, a: unknown, b: unknown) => {
    cases++;
    if (JSON.stringify(a) !== JSON.stringify(b)) { differ++; if (firstDiff.length < 3) firstDiff.push(name); }
  };
  for (const f of FLOORS) {
    const r = f.rect;
    const size = old.rectSizeM(r, f.size, f.ppm);
    for (const reverse of [false, true]) {
      for (const [xw, yw] of PAIRS) {
        const g = rectWalls(r, xw, yw, reverse);
        const [xa, xb] = [g.corners[g.xWall], g.corners[(g.xWall + 1) % 4]];
        const [ya, yb] = [g.corners[g.yWall], g.corners[(g.yWall + 1) % 4]];
        same(`${f.name} lengths`, [wallLengthM(ya, yb, f.size, f.ppm), wallLengthM(xa, xb, f.size, f.ppm)], [size.w, size.h]);
        for (let i = 0; i <= 20; i++) {
          for (let j = 0; j <= 20; j++) {
            const p = { x: i / 20, y: j / 20 };
            same(`${f.name} ${xw}/${yw} distances ${fmt(p)}`, distancesM(g, p, f.size, f.ppm), old.distancesM(r, xw, yw, p, f.size, f.ppm));
            for (const d of [{ x: 2, y: 3 }, { x: 0.37, y: 11.2 }, { x: 50, y: 50 }]) {
              same(`${f.name} ${xw}/${yw} typed ${fmt(p)}`, placeAtDistances(g, p, p, d, f.size, f.ppm), old.pointAtDistances(r, xw, yw, p, d, f.size, f.ppm));
            }
            const ng = guideGeometry(g, p, f.size), og = old.guide(r, xw, yw, p);
            same(`${f.name} ${xw}/${yw} guide ${fmt(p)}`,
              [ng.x.foot, ng.y.foot, span(ng.x.extension, "y"), span(ng.y.extension, "x")],
              [og.xDot, og.yDot, og.xExt && JSON.stringify([...og.xExt].sort()), og.yExt && JSON.stringify([...og.yExt].sort())]);
          }
        }
        // The clicked point on a wall goes into the room, and only one box typed keeps the other coordinate.
        for (const from of [{ x: r.x0, y: r.y0 }, { x: r.x1, y: r.y1 }, { x: r.x0, y: (r.y0 + r.y1) / 2 }]) {
          same(`${f.name} ${xw}/${yw} on a wall`, placeAtDistances(g, from, from, { x: 1, y: 1 }, f.size, f.ppm),
            old.pointAtDistances(r, xw, yw, from, { x: 1, y: 1 }, f.size, f.ppm));
          const onlyY = placeAtDistances(g, from, from, { x: null, y: 1 }, f.size, f.ppm);
          same(`${f.name} ${xw}/${yw} only Y`, onlyY, { x: from.x, y: old.pointAtDistances(r, xw, yw, from, { x: 0, y: 1 }, f.size, f.ppm).y });
        }
      }
    }
  }
  check(22, "a rectangle gives commit 11's distances, typed points and guides, and commit 9's lengths, to the last bit",
    differ === 0, `${cases} cases, ${differ} differ${firstDiff.length ? `: ${firstDiff.join("; ")}` : ""}`);
}

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
