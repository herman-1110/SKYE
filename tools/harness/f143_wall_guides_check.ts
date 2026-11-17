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
// Run with Node, which strips the types itself (Node 23.6 or later; this PC has 24):
//   node tools/harness/f143_wall_guides_check.ts
// (from PowerShell on this PC: Node isn't on Git Bash's PATH). Exit 1 on a failure.
// It needs frontend/utils next to tools/, as in the repo or an export of both.
// No browser, no backend, nothing written.
import {
  distancesM, formatMetres, guideGeometry, guideImageSize, insideRect, nearerEndWall, nearerSideWall,
  parseMetres, parseWallGuides, pointAtDistances, rectFromCorners, serialiseWallGuides, wallGuidesKey,
} from "../../frontend/utils/wallGuides.ts";
import type { EndWall, Frac, ImageSize, SideWall, WallGuides } from "../../frontend/utils/wallGuides.ts";

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

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
