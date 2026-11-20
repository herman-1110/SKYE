"""In-process checks for Prompt 147b: on the exact path a move counts when the
latest exact fix and at least MAN_DOWN_MOVE_CONFIRM_FIXES (3) of the last
MAN_DOWN_MOVE_WINDOW_FIXES (5) are epsilon (2 m) or more from the exact anchor.
The anchor stays at the fix that completed the move, and once
MAN_DOWN_ANCHOR_SETTLE_S (60 s) pass without another it settles to the median,
x and y separately, of the exact fixes since; a cold start settles the same
way. Settling restarts neither the clock nor the latch.

   1  walking end to end through a mid-floor anchor for 3 minutes, never two
      fixes in a row 2 m or more from it: moves keep being counted, at most
      10 s apart, and no red comes; put down, the red comes 60 s after the
      last counted move
   2  jumps while still: single jumps, pairs in a row or apart, before and
      after the anchor settles, and a nudge under 2 m, are no move: the clock
      stays, the red comes once at man_down_minutes, not seen moving
   3  settling after a move: the move's last fix lands 1.5 m off where the
      beacon then lies; 60 s later the anchor is the median of the fixes since
      the move, and noise 2.1 m from that last fix no longer counts. Inside
      the first 60 s the same noise does count, and the red comes later (a
      known cost, Herman's decision D7)
   4  a cold start settles the same way, from a first exact fix 1.5 m off and
      from an approximate placeholder's re-seed; approximate readings stay out
      of the median; inside the first 60 s the noise counts, as in 3
   5  walking after settling, at a 3-minute timer: still for 90 s, then end to
      end through that spot for 4 minutes: the first move within 10 s, moves
      at most 10 s apart, no red while walking; put down, the red comes
      3 minutes after the last counted move
   6  the clock and the latch, at a 2-minute timer: settling at 60 s restarts
      neither (one red, at 120 s, and the latch holds), nor marks the person
      as moving; a counted move restarts both, and the next red comes
      2 minutes after it
   7  the same rule in the amber-to-red upgrade and the restart check: during
      the upgrade's 30 s confirmation the walk pattern of 1 ends the run as
      movement, while a pair of jumps doesn't stop the red at 30 s; after a
      restart, the walk pattern counts as moving, so a new red is raised at
      the old spot without reading /alerts, while jumps don't, and the
      unresolved alert there still holds the red back
   8  the settings: 3, 5 and 60 by default; MAN_DOWN_MOVE_WINDOW_FIXES a whole
      number of at least 1 and no smaller than MAN_DOWN_MOVE_CONFIRM_FIXES,
      MAN_DOWN_ANCHOR_SETTLE_S a positive, finite number; anything else stops
      startup with one sentence naming it, in _load() and in a fresh process
   9  two steps under 2 m each, 3 m in all: a move while the anchor still
      sits at the first spot (its fixes there outnumber the second's); once
      the beacon has lain longer at the second spot, the anchor has followed
      it there, and the same second step isn't a move
   0  the fakes: nothing unimplemented, no tripwire

man_down_minutes is patched (1 unless a check says otherwise) and the clock is
driven by patching safety_service.utcnow_iso; epsilon, the counts, the settling
time and the upgrade's confirmation are the defaults (2.0 m, 3 of 5, 60 s,
30 s). Exact fixes come 2 s apart, as they did live. All coordinates are made
up. On 147's tip (2a627af, 3 in a row and a single-fix anchor) checks 1, 3, 4,
5, 6, 7, 8 and 9 fail; 2 and 0 pass there too.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f147b_move_window_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

BASE_T = datetime(2026, 11, 20, 2, 0, 0, tzinfo=timezone.utc)
EPS = 2.0
CONFIRM, WINDOW, SETTLE = "MAN_DOWN_MOVE_CONFIRM_FIXES", "MAN_DOWN_MOVE_WINDOW_FIXES", "MAN_DOWN_ANCHOR_SETTLE_S"
# A still beacon's spread: offsets of up to 0.23 m, taken in turn, fix by fix.
NOISE = ((0.0, 0.0), (0.2, 0.1), (-0.2, 0.0), (0.1, -0.2), (-0.1, 0.2), (0.15, 0.15), (-0.15, -0.1))
# A walker's sway, up to 0.15 m.
SWAY = ((0.0, 0.0), (0.05, 0.1), (-0.05, -0.05), (0.1, 0.05), (-0.1, -0.1))
HALF = 2.5   # the walk turns 2.5 m either side of the middle: 1.25 m/s, one fix every 2 s

results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


def still_at(spot, k):
    """The k-th fix of a beacon lying at spot."""
    dx, dy = NOISE[k % len(NOISE)]
    return (round(spot[0] + dx, 6), round(spot[1] + dy, 6))


def walk_at(mid, k):
    """The k-th fix of someone walking end to end along x through mid: mid +
    HALF, mid, mid - HALF, mid, ... with a sway. Measured from mid, a fix is
    2.35 m or more away, or 0.15 m or less, and never two in a row are away."""
    dx = (HALF, 0.0, -HALF, 0.0)[k % 4]
    sx, sy = SWAY[k % len(SWAY)]
    return (round(mid[0] + dx + sx, 6), round(mid[1] + sy, 6))


def longest_run_away(points, spot):
    best = run = 0
    for x, y in points:
        run = run + 1 if math.hypot(x - spot[0], y - spot[1]) >= EPS else 0
        best = max(best, run)
    return best


def median_xy(points):
    return (statistics.median(p[0] for p in points), statistics.median(p[1] for p in points))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f147b_move_window_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f147b-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "GO2RTC_CONFIG_PATH": os.path.join(run_dir, "go2rtc.yaml"),
        "HARNESS_SEED_STALE": "0",
    })
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    import harness_fakes
    harness_fakes.install_tripwire(run_dir)
    harness_fakes.install_fakes(run_dir)

    import config.settings as cs
    import services.safety_service as ss
    from firebase_admin import db
    from models.position import PositionRecord
    from models.safety_settings import SafetySettings
    from repositories.alert_repository import alert_repository

    svc = ss.safety_service
    minutes = {"v": 1}
    svc._get_settings = lambda: SafetySettings(man_down_minutes=minutes["v"], collision_distance_m=2.0)
    clock = {"t": 0.0}
    ss.utcnow_iso = lambda: (BASE_T + timedelta(seconds=clock["t"])).isoformat()
    FLOOR = C.FLOOR_ID

    reads = {"n": 0}
    real_get_all = alert_repository.get_all

    def counting_get_all():
        reads["n"] += 1
        return real_get_all()
    alert_repository.get_all = counting_get_all

    def secs(iso):
        s = (datetime.fromisoformat(iso) - BASE_T).total_seconds()
        return int(s) if s == int(s) else s

    def at(t, pid, xy, approx=False):
        """One reading through check_man_down at time t; returns the time, the
        alert raised, and the man-down state after it."""
        clock["t"] = t
        before = reads["n"]
        rec = PositionRecord(beacon_mac=pid, person_id=pid, person_type="worker", x=xy[0], y=xy[1],
                             zone="unknown" if approx else "Z", timestamp=ss.utcnow_iso(),
                             is_approximate=approx, floor_id=FLOOR, building_id=C.BUILDING_ID)
        a = svc.check_man_down(rec)
        tr = ss._man_down_tracker.get(pid)
        run = ss._approx_runs.get(pid)
        return {"t": t, "xy": xy, "approx": approx, "alert": a.alert_type if a else None,
                "anchor": (tr[0], tr[1], secs(tr[2]), tr[3]) if tr else None,
                "latched": pid in ss._still_alerted, "moving": pid in ss._seen_moving,
                "run": (secs(run.started_at), run.alerted) if run else None, "reads": reads["n"] - before}

    def restart():
        """A simulated backend restart: every module-level dict and set in
        safety_service is cleared (the fake RTDB, and so /alerts, survives)."""
        for name, value in list(vars(ss).items()):
            if name.startswith("_") and not name.startswith("__") and isinstance(value, (dict, set)):
                value.clear()

    def fired(steps):
        return [(s["t"], s["alert"]) for s in steps if s["alert"]]

    def moves(steps):
        """The counted moves: an exact fix whose anchor's clock moved to it from
        an earlier exact anchor's (a seed, a cold start or the upgrade's first
        exact fix, isn't one; nor is settling, which never touches the clock)."""
        out = []
        for prev, s in zip(steps, steps[1:]):
            a, b = prev["anchor"], s["anchor"]
            if not s["approx"] and a and b and not a[3] and not b[3] and b[2] == s["t"] and a[2] != s["t"]:
                out.append(s["t"])
        return out

    def gaps(times, start, end):
        pts = [start] + [t for t in times if start < t <= end] + [end]
        return max(b - a for a, b in zip(pts, pts[1:]))

    def stored(pid):
        alerts = (db.reference("/alerts").get() or {}).values()
        return [a["alert_type"] for a in sorted((a for a in alerts if a.get("person_id") == pid),
                                                key=lambda a: a["timestamp"])]

    def near(a, b, tol=1e-9):
        return a is not None and b is not None and abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol

    print(f"[INFO] {CONFIRM}={getattr(ss.settings, CONFIRM, None)} {WINDOW}={getattr(ss.settings, WINDOW, None)} "
          f"{SETTLE}={getattr(ss.settings, SETTLE, None)} (None: not in this code)", flush=True)

    # 1: walking end to end through a mid-floor anchor (1-minute timer). Still
    # at mid for 10 s (the cold start's anchor), the walk from 12 to 190, then
    # put down at one end until 290.
    minutes["v"] = 1
    P, MID = "test-f147b-walk", (3.0, 2.0)
    walk1 = [walk_at(MID, k) for k in range(90)]
    steps = [at(2 * k, P, still_at(MID, k)) for k in range(6)]
    steps += [at(12 + 2 * k, P, walk1[k]) for k in range(90)]
    end_spot = (MID[0] + HALF, MID[1])
    steps += [at(192 + 2 * k, P, still_at(end_spot, k)) for k in range(50)]
    mv = moves(steps)
    walk_mv = [t for t in mv if 12 <= t <= 190]
    reds = fired(steps)
    last = max(mv) if mv else None
    check(1, "walking end to end through a mid-floor anchor (never two fixes in a row 2 m or more from it) for 3 "
             "minutes: moves at most 10 s apart, no red while walking; put down, the red 60 s after the last move",
          longest_run_away(walk1, MID) == 1 and len(walk_mv) >= 15 and gaps(walk_mv, 12, 190) <= 10
          and not [r for r in reds if r[0] <= 190] and last is not None and reds == [(last + 60, "man_down")]
          and 192 <= last <= 200 and steps[-1]["latched"],
          f"most fixes away in a row from the anchor={longest_run_away(walk1, MID)} moves while walking={len(walk_mv)} "
          f"longest gap={gaps(walk_mv, 12, 190) if walk_mv else None} s last move={last} reds={reds}")

    # 2: jumps while still (1-minute timer). Still at S; a single jump at 10, a
    # pair in a row at 24 and 26, a pair apart at 40 and 44, a pair at 70 and
    # 72 after the anchor has settled; from 80 on the beacon is nudged 1.5 m.
    P, S = "test-f147b-jumps", (10.0, 10.0)
    jump = (S[0] + 3.0, S[1])
    nudged = (S[0], S[1] + 1.5)
    steps = []
    for k in range(61):
        t = 2 * k
        xy = jump if t in (10, 24, 26, 40, 44, 70, 72) else still_at(nudged if t >= 80 else S, k)
        steps.append(at(t, P, xy))
    check(2, "jumps while still (one, two in a row, two apart, two after settling) and a 1.5 m nudge: no move, "
             "the clock stays, one red at man_down_minutes, not seen moving",
          moves(steps) == [] and all(s["anchor"][2:] == (0, False) for s in steps)
          and fired(steps) == [(60, "man_down")] and not any(s["moving"] for s in steps) and steps[-1]["latched"],
          f"moves={moves(steps)} clocks={sorted({s['anchor'][2] for s in steps})} fired={fired(steps)} "
          f"moving={any(s['moving'] for s in steps)}")

    # 3: settling after a move (1-minute timer). Both start still at X0 and are
    # carried: 23.0, 24.6 and 26.5 at 10, 12 and 14, a move at 14 whose last
    # fix is 1.5 m past T, where they then lie. The noise is three fixes at
    # 24.4 (2.1 m from 26.5, 0.6 m from T), 4 s apart, with fixes at T between.
    X0, T = (20.0, 5.0), (25.0, 5.0)
    carry = {10: (23.0, 5.0), 12: (24.6, 5.0), 14: (26.5, 5.0)}
    noise = (24.4, 5.0)

    def settle_case(pid, noise_at, until):
        out = []
        for k in range(until // 2 + 1):
            t = 2 * k
            if t < 10:
                xy = still_at(X0, k)
            elif t in carry:
                xy = carry[t]
            else:
                xy = noise if t in noise_at else still_at(T, k)
            out.append(at(t, pid, xy))
        return out
    quiet = settle_case("test-f147b-settle-quiet", (90, 94, 98), 130)
    early = settle_case("test-f147b-settle-early", (30, 34, 38), 130)
    q = {s["t"]: s for s in quiet}
    since_move = [s["xy"] for s in quiet if s["t"] >= 14]
    check(3, "settling after a move: frozen at the move's last fix for 60 s, then the median of the fixes since "
             "the move, and noise 2.1 m from that fix doesn't count; inside the 60 s it does (D7), and the red "
             "comes later",
          moves(quiet) == [14] and q[72]["anchor"] == (26.5, 5.0, 14, False) and q[74]["anchor"][2:] == (14, False)
          and near(q[130]["anchor"], median_xy(since_move)) and abs(q[130]["anchor"][0] - T[0]) < 0.25
          and fired(quiet) == [(74, "man_down")]
          and moves(early) == [14, 38] and early[19]["anchor"] == (noise[0], noise[1], 38, False)
          and fired(early) == [(98, "man_down")],
          f"quiet: moves={moves(quiet)} anchor at 72={q[72]['anchor']} at 130={q[130]['anchor']} "
          f"(median {median_xy(since_move)}) fired={fired(quiet)}; inside 60 s: moves={moves(early)} "
          f"fired={fired(early)}")

    # 4: a cold start settles the same way (1-minute timer). C's first exact
    # fix is 1.5 m past T4, where it lies; noise at 39.4 (2.1 m from the first
    # fix, 0.6 m from T4) after 60 s, and for C2 inside the first 60 s. R
    # starts with approximate readings (a placeholder), its first exact fix at
    # 10 is 1.5 m past T5, and approximate readings far away come at 31 and 45.
    T4, T5, AP_R = (40.0, 5.0), (50.0, 5.0), (56.0, 9.0)
    first4, noise4 = (41.5, 5.0), (39.4, 5.0)

    def cold_case(pid, noise_at, until):
        return [at(2 * k, pid, first4 if k == 0 else (noise4 if 2 * k in noise_at else still_at(T4, k)))
                for k in range(until // 2 + 1)]
    c1 = cold_case("test-f147b-cold", (70, 74, 78), 100)
    c2 = cold_case("test-f147b-cold-early", (20, 24, 28), 100)
    P = "test-f147b-reseed"
    r = [at(t, P, AP_R, approx=True) for t in (0, 4, 8)]
    for k in range(5, 51):
        t = 2 * k
        r.append(at(t, P, (51.5, 5.0) if t == 10 else (noise4[0] + 10.0, 5.0) if t in (80, 84, 88) else still_at(T5, k)))
        if t in (30, 44):
            r.append(at(t + 1, P, AP_R, approx=True))
    c = {s["t"]: s for s in c1}
    rr = {s["t"]: s for s in r}
    r_exact = [s["xy"] for s in r if not s["approx"] and s["t"] >= 10]
    check(4, "a cold start settles the same way: a first fix 1.5 m off, or an approximate placeholder's re-seed, "
             "settles after 60 s to the median of the exact fixes (approximate readings left out), and the noise "
             "then doesn't count; inside the 60 s it does",
          moves(c1) == [] and c[58]["anchor"] == (first4[0], first4[1], 0, False)
          and near(c[100]["anchor"], median_xy([s["xy"] for s in c1])) and fired(c1) == [(60, "man_down")]
          and moves(c2) == [28] and fired(c2) == [(88, "man_down")]
          and moves(r) == [] and rr[68]["anchor"] == (51.5, 5.0, 10, False)
          and near(rr[100]["anchor"], median_xy(r_exact)) and fired(r) == [(70, "man_down")],
          f"first fix off: moves={moves(c1)} anchor at 58={c[58]['anchor']} at 100={c[100]['anchor']} "
          f"fired={fired(c1)}; inside 60 s: moves={moves(c2)} fired={fired(c2)}; re-seed: moves={moves(r)} "
          f"anchor at 68={rr[68]['anchor']} at 100={rr[100]['anchor']} (median {median_xy(r_exact)}) fired={fired(r)}")

    # 5: walking after settling (3-minute timer, as in the live check's L2).
    # Still at MID5 from 0 to 90, walking through it from 92 to 330, then put
    # down at one end until 600.
    minutes["v"] = 3
    P, MID5 = "test-f147b-walk-after", (3.0, 12.0)
    walk5 = [walk_at(MID5, k) for k in range(120)]
    steps = [at(2 * k, P, still_at(MID5, k)) for k in range(46)]
    steps += [at(92 + 2 * k, P, walk5[k]) for k in range(120)]
    end5 = (MID5[0] + HALF, MID5[1])
    steps += [at(332 + 2 * k, P, still_at(end5, k)) for k in range(135)]
    mv = moves(steps)
    walk_mv = [t for t in mv if 92 <= t <= 330]
    reds = fired(steps)
    last = max(mv) if mv else None
    settled = {s["t"]: s for s in steps}[90]["anchor"]
    check(5, "walking after settling (3-minute timer): still for 90 s (the anchor settled), then end to end "
             "through that spot for 4 minutes: the first move within 10 s, moves at most 10 s apart, no red "
             "while walking; put down, the red 3 minutes after the last move",
          abs(settled[0] - MID5[0]) < 0.25 and abs(settled[1] - MID5[1]) < 0.25 and longest_run_away(walk5, MID5) == 1
          and walk_mv and walk_mv[0] <= 102 and gaps(walk_mv, 92, 330) <= 10
          and not [x for x in reds if x[0] <= 330] and last is not None and reds == [(last + 180, "man_down")],
          f"anchor at 90={settled} first move={walk_mv[0] if walk_mv else None} moves while walking={len(walk_mv)} "
          f"longest gap={gaps(walk_mv, 92, 330) if walk_mv else None} s last move={last} reds={reds}")

    # 6: the clock and the latch (2-minute timer). The first fix is 1.0 m off
    # where K lies; still to 200; carried to K2 at 202, 204 and 206; still there.
    minutes["v"] = 2
    P, K, K2 = "test-f147b-clock", (60.0, 5.0), (65.0, 5.0)
    steps = [at(0, P, (61.0, 5.0))] + [at(2 * k, P, still_at(K, k)) for k in range(1, 101)]
    steps += [at(t, P, K2) for t in (202, 204, 206)] + [at(208 + 2 * k, P, still_at(K2, k)) for k in range(62)]
    s6 = {s["t"]: s for s in steps}
    check(6, "the clock and the latch (2-minute timer): settling at 60 s moves the anchor but restarts neither "
             "the clock nor the latch (one red, at 120 s) and isn't moving; a counted move restarts both",
          s6[58]["anchor"] == (61.0, 5.0, 0, False) and s6[60]["anchor"][2:] == (0, False)
          and abs(s6[60]["anchor"][0] - 61.0) > 0.5 and all(s6[t]["anchor"][2] == 0 for t in range(0, 201, 2))
          and s6[200]["latched"] and not s6[200]["moving"]
          and (s6[206]["anchor"], s6[206]["latched"], s6[206]["moving"]) == ((65.0, 5.0, 206, False), False, True)
          and fired(steps) == [(120, "man_down"), (326, "man_down")],
          f"anchor at 58={s6[58]['anchor']} at 60={s6[60]['anchor']} at 200: latched={s6[200]['latched']} "
          f"moving={s6[200]['moving']}; at 206={s6[206]['anchor']} latched={s6[206]['latched']} "
          f"moving={s6[206]['moving']}; fired={fired(steps)}")

    # 7: the same rule in the upgrade and the restart check (1-minute timer).
    # The upgrade: an amber from approximate readings at AP_U up to 60, the
    # first exact fix at 70 (U). UA then walks through U as in 1; UB lies at U
    # with a pair of jumps at 74 and 76.
    minutes["v"] = 1
    AP_U, U = (70.0, 2.0), (70.5, 2.5)
    ua, ub = "test-f147b-upgrade-walk", "test-f147b-upgrade-jumps"
    up_walk = [at(t, ua, AP_U, approx=True) for t in range(0, 61, 10)] + [at(70, ua, U)]
    up_walk += [at(72 + 2 * k, ua, walk_at(U, k)) for k in range(30)]
    up_jump = [at(t, ub, AP_U, approx=True) for t in range(0, 61, 10)] + [at(70, ub, U)]
    up_jump += [at(t, ub, (U[0] + 3.5, U[1]) if t in (74, 76) else still_at(U, t)) for t in range(72, 121, 2)]
    wa = {s["t"]: s for s in up_walk}
    upgrade_ok = (fired(up_walk) == [(60, "possible_man_down")] and moves(up_walk)[:1] == [80]
                  and wa[78]["run"] is not None and wa[80]["run"] is None and wa[80]["moving"]
                  and fired(up_jump) == [(60, "possible_man_down"), (100, "man_down")] and moves(up_jump) == []
                  and not any(s["moving"] for s in up_jump))
    # The restart check. Before: RC and RD lie still at their spots and get
    # their red at 60, left unresolved. A restart. After: RC lies at its spot
    # from 1000, walks through it as in 1 from 1012 to 1100, and is put down
    # there again; RD lies at its spot with a jump at 1010 and two at 1030 and
    # 1032.
    rc, rd, SC, SD = "test-f147b-restart-walk", "test-f147b-restart-jumps", (80.0, 5.0), (90.0, 5.0)
    before_c = [at(2 * k, rc, still_at(SC, k)) for k in range(36)]
    before_d = [at(2 * k, rd, still_at(SD, k)) for k in range(36)]
    restart()
    after_c = [at(1000 + 2 * k, rc, still_at(SC, k)) for k in range(6)]
    after_c += [at(1012 + 2 * k, rc, walk_at(SC, k)) for k in range(45)]
    after_c += [at(1102 + 2 * k, rc, still_at(SC, k)) for k in range(50)]
    after_d = [at(1000 + 2 * k, rd, (SD[0] + 3.0, SD[1]) if 1000 + 2 * k in (1010, 1030, 1032) else still_at(SD, k))
               for k in range(51)]
    restart_ok = (fired(before_c) == [(60, "man_down")] and fired(before_d) == [(60, "man_down")]
                  and len(moves(after_c)) >= 10 and after_c[-1]["moving"] and len(fired(after_c)) == 1
                  and sum(s["reads"] for s in after_c) == 0 and stored(rc) == ["man_down", "man_down"]
                  and fired(after_d) == [] and moves(after_d) == [] and not after_d[-1]["moving"]
                  and after_d[-1]["latched"] and sum(s["reads"] for s in after_d) == 1 and stored(rd) == ["man_down"])
    check(7, "the same rule in the upgrade (the walk pattern ends the run as movement; a pair of jumps doesn't stop "
             "the red at 30 s) and the restart check (the walk pattern counts as moving: a new red without reading "
             "/alerts; jumps don't: the unresolved alert holds the red back)",
          upgrade_ok and restart_ok,
          f"upgrade walk: fired={fired(up_walk)} first move={moves(up_walk)[:1]} run at 78/80="
          f"{wa[78]['run'] is not None}/{wa[80]['run'] is not None}; upgrade jumps: fired={fired(up_jump)} "
          f"moves={moves(up_jump)}; restart walk: moves={len(moves(after_c))} fired={fired(after_c)} "
          f"reads={sum(s['reads'] for s in after_c)} stored={stored(rc)}; restart jumps: fired={fired(after_d)} "
          f"moves={moves(after_d)} reads={sum(s['reads'] for s in after_d)} stored={stored(rd)}")

    # 8: the settings
    names = (CONFIRM, WINDOW, SETTLE)

    def load_with(values):
        saved = {n: os.environ.pop(n, None) for n in names}
        try:
            os.environ.update(values)
            got = cs._load()
            return tuple(getattr(got, n, "absent") for n in names)
        except Exception as e:
            return f"{type(e).__name__}: {e}"
        finally:
            for n in names:
                os.environ.pop(n, None)
                if saved[n] is not None:
                    os.environ[n] = saved[n]

    def whole(v):
        return f"ValueError: {WINDOW} must be a whole number of at least 1, not {v!r}."

    def seconds(v):
        return f"ValueError: {SETTLE} must be a positive number of seconds, not {v!r}."

    def larger(c, w):
        return f"ValueError: {CONFIRM} ({c}) can't be larger than {WINDOW} ({w})."

    default = load_with({})
    good = {"1 of 1": load_with({CONFIRM: "1", WINDOW: "1"}), "5 of 5": load_with({CONFIRM: "5", WINDOW: "5"}),
            "2 of 7": load_with({CONFIRM: "2", WINDOW: "7"}), "0.5 s": load_with({SETTLE: "0.5"}),
            "1e2 s": load_with({SETTLE: "1e2"}), "' 90 ' s": load_with({SETTLE: " 90 "})}
    want = {"1 of 1": (1, 1, 60.0), "5 of 5": (5, 5, 60.0), "2 of 7": (2, 7, 60.0), "0.5 s": (3, 5, 0.5),
            "1e2 s": (3, 5, 100.0), "' 90 ' s": (3, 5, 90.0)}
    bad_w = {v: load_with({WINDOW: v}) for v in ("0", "-1", "2.5", "five", "")}
    bad_s = {v: load_with({SETTLE: v}) for v in ("0", "-5", "nan", "inf", "-inf", "abc", "")}
    bad_cw = {"4 of 3": load_with({CONFIRM: "4", WINDOW: "3"}), "3 of 2": load_with({WINDOW: "2"})}

    def child(values):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", **values)
        try:
            p = subprocess.run([sys.executable, "-B", "-c", "import config.settings"], cwd=backend_dir, env=env,
                               capture_output=True, text=True, timeout=120)
            return p.returncode, (p.stderr.strip().splitlines() or [""])[-1]
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"
    child_s, child_cw = child({SETTLE: "0"}), child({WINDOW: "2"})
    check(8, "the settings: 3, 5 and 60 by default; the window a whole number of at least 1 and no smaller than "
             "the confirm count, the settling time positive and finite; anything else stops startup with one "
             "sentence (in _load() and in a fresh process)",
          default == (3, 5, 60.0) and good == want and all(bad_w[v] == whole(v) for v in bad_w)
          and all(bad_s[v] == seconds(v) for v in bad_s)
          and bad_cw == {"4 of 3": larger(4, 3), "3 of 2": larger(3, 2)}
          and child_s[0] not in (0, None) and child_s[1] == seconds("0")
          and child_cw[0] not in (0, None) and child_cw[1] == larger(3, 2),
          f"default={default} good={good} window={bad_w} settle={bad_s} confirm>window={bad_cw} "
          f"child: settle 0 -> {child_s}, window 2 -> {child_cw}")

    # 9: two steps under 2 m each (1-minute timer). Still at S9 from 0 to 90,
    # nudged 1.5 m and left there, then 1.5 m further, 3 m from S9. N lies
    # 40 s at the middle spot (fewer fixes than at S9), N2 120 s (more).
    S9 = (100.0, 5.0)
    mid9, far9 = (S9[0] + 1.5, S9[1]), (S9[0] + 3.0, S9[1])

    def steps_case(pid, middle_s, until):
        out = []
        for k in range(until // 2 + 1):
            t = 2 * k
            spot = S9 if t <= 90 else mid9 if t <= 90 + middle_s else far9
            out.append(at(t, pid, still_at(spot, k)))
        return out
    n1 = steps_case("test-f147b-two-steps", 40, 200)
    n2 = steps_case("test-f147b-two-steps-late", 120, 300)
    n2_end = n2[-1]["anchor"]
    check(9, "two steps under 2 m each, 3 m in all: a move while the anchor still sits at the first spot; once "
             "the beacon has lain longer at the second, the anchor has followed it, and the second step isn't one",
          moves(n1) == [136] and moves(n2) == [] and abs(n2_end[0] - far9[0]) < 2.0 and n2_end[0] > mid9[0] - 0.25,
          f"40 s at the middle: moves={moves(n1)}; 120 s: moves={moves(n2)} anchor at the end={n2_end}")

    loud = [p for p in ("UNIMPLEMENTED.txt", "TRIPWIRE_HIT.txt") if os.path.exists(os.path.join(run_dir, p))]
    check(0, "fakes: nothing unimplemented, no tripwire", not loud, f"{loud}")
    failed = [x for x in results if not x["ok"]]
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"passed": len(results) - len(failed), "failed": len(failed), "results": results}, f, indent=1)
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
