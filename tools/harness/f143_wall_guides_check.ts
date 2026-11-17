// Checks for Prompt 143's placement-guide maths, frontend/utils/wallGuides.ts (D1).
//
//   1  X and Y for each pair of walls (left/right with top/bottom)
//   2  a point outside the rectangle: distances, and where the walls are extended
//   3  fractions -> metres -> fractions round-trips, inside and outside, every pair
//   4  typed X and Y give the right point: on each side of a wall, from a point on
//      the wall, clamped at the image's edge, and on the real floor's numbers
//   5  agreement with the backend's floor_service.derive_ap_metres()
//   6  the localStorage value: its key, a round trip, and bad values read as none
//   7  the rectangle from a drag, and which wall a click picks
//   8  metres shown to 2 decimal places; typed metres parsed
//   9  the pixel size used: the floor's stored size, else the image's natural size
//
// And for D2, the camera's direction (frontend/utils/cameraFacing.ts):
//  10  0 is up and angles go clockwise, with y growing downward: 90 right, 180 down
//  11  the angle from a camera to the cursor is worked out in pixels, not fractions
//  12  rounding for the handle wraps 359.6 to 0; compass words; the "135° (SE)" label
//  13  the cone's outline and the handle's tip point the right way; the dialog's boxes
//
// And for the room's outline (Herman, 18 Nov):
//  14  the room's width and height in metres, from the floor's px/m
//  15  the width is the X a device on the far side wall reads; the height, its Y on the far end wall
//
// Run with Node, which strips the types itself (Node 23.6 or later; this PC has 24):
//   node tools/harness/f143_wall_guides_check.ts
// (from PowerShell on this PC: Node isn't on Git Bash's PATH). Exit 1 on a failure.
// It needs frontend/utils next to tools/, as in the repo or an export of both.
// No browser, no backend, nothing written.
import {
  distancesM, formatMetres, guideGeometry, guideImageSize, insideRect, nearerEndWall, nearerSideWall,
  parseMetres, parseWallGuides, pointAtDistances, rectFromCorners, rectSizeM, serialiseWallGuides, wallGuidesKey,
} from "../../frontend/utils/wallGuides.ts";
import type { EndWall, Frac, ImageSize, SideWall, WallGuides, WallRect } from "../../frontend/utils/wallGuides.ts";
import {
  compassWord, conePath, facingBetween, facingFromVector, facingLabel, facingVector, normaliseFacing,
  parseFacing, parseFov, roundFacing,
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
// A room from 2 to 14 m across and 3.2 to 14.4 m down the harness floor.
const RECT = { x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.9 };
const PAIRS: [SideWall, EndWall][] = [["left", "top"], ["left", "bottom"], ["right", "top"], ["right", "bottom"]];
const walls = (xWall: SideWall, yWall: EndWall): WallGuides => ({ rect: RECT, xWall, yWall });

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
  const g = guideGeometry(walls("left", "top"), Q);
  const inside = guideGeometry(walls("left", "top"), { x: 0.3, y: 0.4 });
  const ok = near(lt.x, 1) && near(lt.y, 12) && near(rb.x, 13) && near(rb.y, 0.8)
    && !insideRect(RECT, Q) && !g.inside
    && g.xDot.x === 0.1 && g.xDot.y === 0.95 && g.yDot.x === 0.05 && g.yDot.y === 0.2
    && g.xWallExtension?.[0] === 0.9 && g.xWallExtension?.[1] === 0.95
    && g.yWallExtension?.[0] === 0.05 && g.yWallExtension?.[1] === 0.1
    && inside.inside && inside.xWallExtension === null && inside.yWallExtension === null;
  check(2, "a point outside the rectangle: its distances, and the walls extended to its dots", ok,
    `left/top X ${formatMetres(lt.x)} Y ${formatMetres(lt.y)}; right/bottom X ${formatMetres(rb.x)} Y ${formatMetres(rb.y)}; `
    + `extensions ${JSON.stringify(g.xWallExtension)} ${JSON.stringify(g.yWallExtension)}`);
}

// 3. Round trips over a grid that reaches outside the room on every side.
{
  let worst = 0, n = 0;
  for (const [xw, yw] of PAIRS) {
    const g = walls(xw, yw);
    for (let i = 0; i <= 20; i++) {
      for (let j = 0; j <= 20; j++) {
        const p = { x: i / 20, y: j / 20 };
        const back = pointAtDistances(g, p, distancesM(g, p, HARNESS, PPM), HARNESS, PPM);
        worst = Math.max(worst, Math.abs(back.x - p.x), Math.abs(back.y - p.y));
        n++;
      }
    }
  }
  check(3, "fractions -> metres -> fractions round-trips (inside and outside, every pair of walls)",
    worst < 1e-12, `${n} points, worst error ${worst.toExponential(2)} of the image`);
}

// 4. Typed distances.
{
  const lt = walls("left", "top"), rb = walls("right", "bottom");
  const cases: { name: string; got: Frac; want: Frac }[] = [
    { name: "inside, left/top", got: pointAtDistances(lt, { x: 0.3, y: 0.4 }, { x: 2, y: 3 }, HARNESS, PPM), want: { x: 0.2, y: 0.3875 } },
    { name: "inside, right/bottom", got: pointAtDistances(rb, { x: 0.3, y: 0.4 }, { x: 2, y: 3 }, HARNESS, PPM), want: { x: 0.6, y: 0.7125 } },
    { name: "clicked left of the left wall", got: pointAtDistances(lt, { x: 0.05, y: 0.4 }, { x: 1.5, y: 3 }, HARNESS, PPM), want: { x: 0.025, y: 0.3875 } },
    { name: "clicked above the top wall", got: pointAtDistances(lt, { x: 0.3, y: 0.1 }, { x: 2, y: 0.8 }, HARNESS, PPM), want: { x: 0.2, y: 0.15 } },
    { name: "clicked on the walls: into the room", got: pointAtDistances(lt, { x: 0.1, y: 0.2 }, { x: 2, y: 3 }, HARNESS, PPM), want: { x: 0.2, y: 0.3875 } },
    { name: "on the right/bottom walls: into the room", got: pointAtDistances(rb, { x: 0.7, y: 0.9 }, { x: 2, y: 3 }, HARNESS, PPM), want: { x: 0.6, y: 0.7125 } },
    { name: "past the image's edge: clamped", got: pointAtDistances(lt, { x: 0.3, y: 0.4 }, { x: 50, y: 50 }, HARNESS, PPM), want: { x: 1, y: 1 } },
  ];
  const bad = cases.filter((c) => !near(c.got.x, c.want.x) || !near(c.got.y, c.want.y));
  // As the guide itself reads them: typed 2.00 and 3.00 read back as 2.00 and 3.00.
  const readsHarness = distancesM(lt, cases[0].got, HARNESS, PPM);
  const realWalls: WallGuides = { rect: { x0: 0.12, y0: 0.08, x1: 0.83, y1: 0.91 }, xWall: "left", yWall: "top" };
  const realPoint = pointAtDistances(realWalls, { x: 0.5, y: 0.5 }, { x: 2, y: 3 }, REAL, REAL_PPM);
  const readsReal = distancesM(realWalls, realPoint, REAL, REAL_PPM);
  const clampedReads = distancesM(lt, cases[6].got, HARNESS, PPM);
  check(4, "typed X and Y give the right point, read back by the guide as typed (well within 1 cm)",
    bad.length === 0 && near(readsHarness.x, 2) && near(readsHarness.y, 3) && near(readsReal.x, 2) && near(readsReal.y, 3)
      && near(clampedReads.x, 18) && near(clampedReads.y, 12.8),
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
  const corner: WallGuides = { rect: { x0: 0, y0: 0, x1: 1, y1: 1 }, xWall: "left", yWall: "top" };
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
  const bad = ["", "not json", "null", "[]", "{}", "42",
    JSON.stringify({ rect: { x0: 0.1, y0: 0.2, x1: 0.7, y1: 1.2 }, xWall: "left", yWall: "top" }),
    JSON.stringify({ rect: { x0: -0.1, y0: 0.2, x1: 0.7, y1: 0.9 }, xWall: "left", yWall: "top" }),
    JSON.stringify({ rect: { x0: 0.7, y0: 0.2, x1: 0.1, y1: 0.9 }, xWall: "left", yWall: "top" }),
    JSON.stringify({ rect: { x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.2 }, xWall: "left", yWall: "top" }),
    JSON.stringify({ rect: { x0: "0.1", y0: 0.2, x1: 0.7, y1: 0.9 }, xWall: "left", yWall: "top" }),
    JSON.stringify({ rect: { x0: 0.1, y0: 0.2, x1: 0.7 }, xWall: "left", yWall: "top" }),
    JSON.stringify({ rect: { x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.9 }, xWall: "top", yWall: "left" }),
    JSON.stringify({ rect: { x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.9 }, xWall: "left" }),
    JSON.stringify({ xWall: "left", yWall: "top" }),
  ];
  const accepted = bad.filter((s) => parseWallGuides(s) !== null);
  check(6, "localStorage: the key, a round trip, and bad values read as no walls",
    wallGuidesKey("355d6a73-floor") === "skye-wall-guides:355d6a73-floor" && parseWallGuides(null) === null
      && JSON.stringify(back) === JSON.stringify(g) && accepted.length === 0,
    `round trip ${JSON.stringify(back) === JSON.stringify(g)}; ${bad.length - accepted.length} of ${bad.length} bad values refused`);
}

// 7. The rectangle a drag spans, and the walls a click picks.
{
  const r = rectFromCorners({ x: 0.7, y: 0.9 }, { x: 0.1, y: 0.2 });
  const clamped = rectFromCorners({ x: -0.5, y: 0.5 }, { x: 0.5, y: 1.7 });
  const ok = JSON.stringify(r) === JSON.stringify(RECT)
    && JSON.stringify(clamped) === JSON.stringify({ x0: 0, y0: 0.5, x1: 0.5, y1: 1 })
    && nearerSideWall(RECT, { x: 0.2, y: 0.5 }) === "left" && nearerSideWall(RECT, { x: 0.65, y: 0.5 }) === "right"
    && nearerSideWall(RECT, { x: 0.95, y: 0.1 }) === "right" && nearerEndWall(RECT, { x: 0.4, y: 0.25 }) === "top"
    && nearerEndWall(RECT, { x: 0.4, y: 0.85 }) === "bottom" && nearerEndWall(RECT, { x: 0.4, y: 0.0 }) === "top";
  check(7, "the rectangle from a drag (either direction, clamped), and the nearer wall a click picks", ok,
    `rect ${JSON.stringify(r)} clamped ${JSON.stringify(clamped)}`);
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

// The room's outline (Herman, 18 Nov): a room on the 597 x 450 floor, and the two floors.
const REAL_ROOM: WallRect = { x0: 0.12, y0: 0.08, x1: 0.83, y1: 0.91 };
const FLOORS: { name: string; size: ImageSize; ppm: number; rect: WallRect }[] = [
  { name: "harness", size: HARNESS, ppm: PPM, rect: RECT },
  { name: "597 x 450", size: REAL, ppm: REAL_PPM, rect: REAL_ROOM },
];

// 14. Width = (x1 - x0) x width ÷ px/m and height = (y1 - y0) x height ÷ px/m. RECT is
// 12 m by 11.2 m on the harness floor; REAL_ROOM is 0.71 x 597 ÷ 46.08 by 0.83 x 450 ÷ 46.08.
{
  const harness = rectSizeM(RECT, HARNESS, PPM);
  const real = rectSizeM(REAL_ROOM, REAL, REAL_PPM);
  const whole = rectSizeM(rectFromCorners({ x: -0.3, y: 1.4 }, { x: 1.2, y: -0.1 }), HARNESS, PPM);   // dragged past the image
  const press = rectSizeM(rectFromCorners({ x: 0.4, y: 0.4 }, { x: 0.4, y: 0.4 }), HARNESS, PPM);   // the press, before any move
  const ok = near(harness.w, 12) && near(harness.h, 11.2)
    && near(real.w, 9.198567708333333) && near(real.h, 8.10546875)
    && formatMetres(real.w) === "9.20" && formatMetres(real.h) === "8.11"
    && whole.w === 20 && whole.h === 16 && press.w === 0 && press.h === 0;
  check(14, "the room's width and height in metres from the floor's px/m (a drag past the image counts to its edge)", ok,
    `harness ${formatMetres(harness.w)} x ${formatMetres(harness.h)} m; 597 x 450 floor ${formatMetres(real.w)} x ${formatMetres(real.h)} m; `
    + `past the edges ${formatMetres(whole.w)} x ${formatMetres(whole.h)} m`);
}

// 15. The lengths and the guides agree to the last bit: on the far side wall a device reads
// X = the width, and on the far end wall Y = the height, whichever walls are picked.
{
  const cases: { name: string; got: number; want: number }[] = [];
  for (const f of FLOORS) {
    const s = rectSizeM(f.rect, f.size, f.ppm);
    const g = (xWall: SideWall, yWall: EndWall): WallGuides => ({ rect: f.rect, xWall, yWall });
    const mid = { x: (f.rect.x0 + f.rect.x1) / 2, y: (f.rect.y0 + f.rect.y1) / 2 };
    cases.push(
      { name: `${f.name}, X from the left wall at the right wall`, got: distancesM(g("left", "top"), { x: f.rect.x1, y: mid.y }, f.size, f.ppm).x, want: s.w },
      { name: `${f.name}, X from the right wall at the left wall`, got: distancesM(g("right", "top"), { x: f.rect.x0, y: mid.y }, f.size, f.ppm).x, want: s.w },
      { name: `${f.name}, Y from the top wall at the bottom wall`, got: distancesM(g("left", "top"), { x: mid.x, y: f.rect.y1 }, f.size, f.ppm).y, want: s.h },
      { name: `${f.name}, Y from the bottom wall at the top wall`, got: distancesM(g("left", "bottom"), { x: mid.x, y: f.rect.y0 }, f.size, f.ppm).y, want: s.h },
    );
  }
  const bad = cases.filter((c) => c.got !== c.want);
  check(15, "the width is the X a device on the far side wall reads, the height its Y on the far end wall (identical)",
    bad.length === 0, bad.length ? `differ: ${bad.map((c) => c.name).join("; ")}` : `${cases.length} of ${cases.length} identical`);
}

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
