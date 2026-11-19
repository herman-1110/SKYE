"""In-process checks for Prompt 147: on the exact path, a move needs
MAN_DOWN_MOVE_CONFIRM_FIXES (3) exact fixes in a row, each epsilon (2 m) or
more from the exact anchor. One fix like that alone (a lone jump) is counted
and changes nothing else.

   1  a still person with lone jumps (one fix away and back, then two away and
      back) keeps their anchor and clock, and gets their red at
      man_down_minutes; a jump that lands when the red is due raises nothing,
      and the red comes on the next fix back
   2  three fixes in a row epsilon or more away: the first two change nothing
      (the anchor, its clock and the latch stay, not seen moving); the third
      re-anchors there, restarts the clock, clears the latch and marks the
      person as seen moving, and the next red comes man_down_minutes after it
   3  a fix within epsilon between away fixes resets the count
   4  approximate readings between away fixes neither count nor reset it, and
      leave the exact anchor alone
   5  someone walking steadily (1.2 m/s, a fix every 2 s) is re-anchored at
      least every third fix and never alerted
   6  the upgrade from amber to red: a lone jump during the 30 s confirmation
      doesn't end the run, which keeps confirming from its first exact fix,
      and the red comes at 30 s; three fixes in a row away end the run as
      movement
   7  after a simulated restart, lone jumps don't count as having moved, so an
      unresolved alert for the same spot still stops a repeat (Prompt 145, D3)
   8  with the setting at 1, the same inputs give the results of the code
      before 147 (recorded on e632d13 with --print-n1)
   9  the setting: 3 by default; 1 and 4 accepted; 0, a negative number, a
      fraction, a word or an empty value stop startup with one sentence
      naming it, in _load() and in a fresh process importing config.settings
   0  the fakes: nothing unimplemented, no tripwire

man_down_minutes is patched to 1 and the clock is driven by patching
safety_service.utcnow_iso; epsilon and the confirmation time are the defaults
(2.0 m, 30 s). Exact fixes come 2 s apart, as they did live on 19 Nov. All
coordinates are made up. On e632d13 (before 147), checks 1, 2, 3, 4, 6, 7 and
9 fail; 5 and 8 pass there too.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f147_move_confirm_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

BASE_T = datetime(2026, 11, 19, 2, 0, 0, tzinfo=timezone.utc)
NAME = "MAN_DOWN_MOVE_CONFIRM_FIXES"
SPOT = (5.0, 5.0)
JITTER = (5.3, 5.1)       # 0.32 m from SPOT: the same spot, read again
JUMP = (8.0, 5.0)         # 3 m from SPOT, 2.7 m from JITTER: past the 2 m epsilon
FAR = (12.0, 5.0)         # 7 m away
AP1 = (2.0, 2.0)          # an approximate reading's x/y is the strongest AP's own
U = (2.5, 2.5)            # the upgrade's first exact fix, near AP1
U_JIT = (2.6, 2.5)
U_JUMP = (6.0, 2.5)       # 3.5 m from U
U_FAR = (9.0, 9.0)
WOBBLE = (0.0, 0.15, -0.15, 0.1, -0.1, 0.05)

# Check 8: what e632d13 (before 147, where one fix past epsilon is a move)
# returns for the inputs of checks 1-7, printed by --print-n1 on that code.
# Per input: the alerts (time, type); every change of anchor (time, x, y, its
# clock, approximate), for the walker how many anchors and the most fixes
# between two; seen moving and the latch at the end.
TODAY = {
    "1a": {"fired": [], "anchors": [(0, 5.0, 5.0, 0, False), (20, 8.0, 5.0, 20, False), (22, 5.3, 5.1, 22, False),
                                     (40, 8.0, 5.0, 40, False), (44, 5.0, 5.0, 44, False)],
           "moving": True, "latched": False},
    "1b": {"fired": [], "anchors": [(0, 5.0, 5.0, 0, False), (60, 8.0, 5.0, 60, False), (62, 5.0, 5.0, 62, False)],
           "moving": True, "latched": False},
    "2": {"fired": [(60, "man_down"), (130, "man_down")],
          "anchors": [(0, 5.0, 5.0, 0, False), (70, 12.0, 5.0, 70, False)], "moving": True, "latched": True},
    "3": {"fired": [], "anchors": [(0, 5.0, 5.0, 0, False), (10, 12.0, 5.0, 10, False), (14, 5.3, 5.1, 14, False),
                                    (16, 12.0, 5.0, 16, False)],
          "moving": True, "latched": False},
    "4": {"fired": [], "anchors": [(0, 5.0, 5.0, 0, False), (10, 12.0, 5.0, 10, False)],
          "moving": True, "latched": False},
    "5": {"fired": [], "anchors": (90, 1), "moving": True, "latched": False},
    "6a": {"fired": [(60, "possible_man_down")],
           "anchors": [(0, 2.0, 2.0, 0, True), (70, 2.5, 2.5, 0, False), (80, 6.0, 2.5, 80, False),
                       (90, 2.6, 2.5, 90, False)],
           "moving": True, "latched": False},
    "6b": {"fired": [(60, "possible_man_down")],
           "anchors": [(0, 2.0, 2.0, 0, True), (70, 2.5, 2.5, 0, False), (80, 9.0, 9.0, 80, False)],
           "moving": True, "latched": False},
    "7": {"fired": [(60, "man_down"), (1094, "man_down")],
          "anchors": [(0, 5.0, 5.0, 0, False), (1000, 5.3, 5.1, 1000, False), (1010, 8.0, 5.0, 1010, False),
                      (1012, 5.3, 5.1, 1012, False), (1030, 8.0, 5.0, 1030, False), (1034, 5.3, 5.1, 1034, False)],
          "moving": True, "latched": True},
    "7-reads": 0,
    "7-stored": ["man_down", "man_down"],
}

results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    ap.add_argument("--print-n1", action="store_true", help="print check 8's results at 1 (to record TODAY)")
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f147_move_confirm_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f147-default-rtdb.firebaseio.com",
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
    svc._get_settings = lambda: SafetySettings(man_down_minutes=1, collision_distance_m=2.0)
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
        if not iso:
            return None
        s = (datetime.fromisoformat(iso) - BASE_T).total_seconds()
        return int(s) if s == int(s) else s

    def snap(pid):
        tr = ss._man_down_tracker.get(pid)
        run = ss._approx_runs.get(pid)
        return {
            "anchor": (tr[0], tr[1], secs(tr[2]), tr[3]) if tr else None,
            "latched": pid in ss._still_alerted,
            "moving": pid in ss._seen_moving,
            "count": getattr(ss, "_move_count", {}).get(pid, 0),   # none before 147
            "run": (run.x, run.y, secs(run.started_at), secs(run.confirming_since), run.alerted) if run else None,
        }

    def at(t, pid, xy, approx=False):
        clock["t"] = t
        rec = PositionRecord(beacon_mac=pid, person_id=pid, person_type="worker", x=xy[0], y=xy[1],
                             zone="unknown" if approx else "Z", timestamp=ss.utcnow_iso(),
                             is_approximate=approx, floor_id=FLOOR, building_id=C.BUILDING_ID)
        a = svc.check_man_down(rec)
        return dict(t=t, alert=a.alert_type if a else None, **snap(pid))

    def restart():
        for name in ("_stale_alerted", "_last_man_down", "_still_alerted", "_man_down_tracker",
                     "_approx_runs", "_last_fresh_mono", "_held_logged", "_seen_moving", "_move_count"):
            if hasattr(ss, name):
                getattr(ss, name).clear()
        reads["n"] = 0

    def by_t(steps):
        return {s["t"]: s for s in steps}

    def fired(steps):
        return [(s["t"], s["alert"]) for s in steps if s["alert"]]

    def stored(pid):
        alerts = (db.reference("/alerts").get() or {}).values()
        return [a["alert_type"] for a in sorted((a for a in alerts if a.get("person_id") == pid),
                                                key=lambda a: a["timestamp"])]

    def scenarios(prefix):
        """The inputs of checks 1-7, each for its own person. Returns their
        steps: each call's time, alert and the man-down state after it."""
        out = {}
        # 1a: lone jumps while still. A fix every 2 s at SPOT or JITTER; one
        # jump at 20 and back at 22; two at 40 and 42 and back at 44.
        p = prefix + "lone-jumps"
        out["1a"] = [at(t, p, JUMP if t in (20, 40, 42) else (SPOT if t % 4 == 0 else JITTER))
                     for t in range(0, 71, 2)]
        # 1b: a jump at 60, when the red is due
        p = prefix + "jump-when-due"
        out["1b"] = [at(t, p, JUMP if t == 60 else SPOT) for t in range(0, 71, 2)]
        # 2: still to 60 (the red), then FAR at 70, 72 and 74, then still at FAR
        p = prefix + "real-move"
        out["2"] = [at(t, p, SPOT) for t in range(0, 61, 2)] + [at(t, p, FAR) for t in range(70, 141, 2)]
        # 3: two away, one back within epsilon at 14, then three away from 16
        p = prefix + "back-between"
        out["3"] = [at(t, p, FAR if t in (10, 12) or t >= 16 else (SPOT if t == 0 else JITTER))
                    for t in range(0, 31, 2)]
        # 4: exact away fixes at 10, 14 and 18, approximate readings at 12, 16 and 17
        p = prefix + "approx-between"
        steps = [at(t, p, SPOT if t == 0 else JITTER) for t in range(0, 9, 2)]
        for t in (10, 12, 14, 16, 17, 18):
            steps.append(at(t, p, AP1, approx=True) if t in (12, 16, 17) else at(t, p, FAR))
        out["4"] = steps
        # 5: walking along a corridor at 1.2 m/s with a small wobble, a fix every 2 s, for 3 minutes
        p = prefix + "walker"
        out["5"] = [at(2 * k, p, (1.0 + 2.4 * k + WOBBLE[k % len(WOBBLE)], 5.0)) for k in range(90)]
        # 6a: the amber at 60; the first exact fix at 70; a lone jump at 80; back at 90 and 100
        p = prefix + "upgrade-jump"
        steps = [at(t, p, AP1, approx=True) for t in range(0, 61, 10)]
        steps += [at(70, p, U), at(80, p, U_JUMP), at(90, p, U_JIT), at(100, p, U), at(110, p, U_JIT)]
        out["6a"] = steps
        # 6b: the amber at 60; the first exact fix at 70; U_FAR at 80, 82 and 84, then still there
        p = prefix + "upgrade-move"
        steps = [at(t, p, AP1, approx=True) for t in range(0, 61, 10)]
        steps += [at(70, p, U)] + [at(t, p, U_FAR) for t in range(80, 111, 2)]
        out["6b"] = steps
        # 7: still to 70 (the red at 60); a restart; still at JITTER from 1000
        # to 1100 with a lone jump at 1010 and two at 1030 and 1032
        p = prefix + "restart"
        before = [at(t, p, SPOT) for t in range(0, 71, 2)]
        restart()
        after = [at(t, p, JUMP if t in (1010, 1030, 1032) else JITTER) for t in range(1000, 1101, 2)]
        out["7"] = before + after
        out["7-reads"] = reads["n"]
        out["7-stored"] = stored(p)
        return out

    def summary(out):
        """Check 8's comparison: per input, the alerts, every change of anchor
        (time, x, y, clock, approximate), and seen moving and the latch at
        the end; for the walker, how many anchors and the most fixes between
        two of them. The count isn't compared: there's none before 147."""
        res = {}
        for key, steps in out.items():
            if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
                res[key] = steps
                continue
            changes, prev = [], None
            for s in steps:
                if s["anchor"] != prev:
                    changes.append((s["t"],) + (tuple(s["anchor"]) if s["anchor"] else (None,)))
                    prev = s["anchor"]
            if key == "5":
                idx = [i for i in range(len(steps)) if i == 0 or steps[i]["anchor"] != steps[i - 1]["anchor"]]
                changes = (len(idx), max(b - a for a, b in zip(idx, idx[1:])) if len(idx) > 1 else None)
            res[key] = {"fired": fired(steps), "anchors": changes,
                        "moving": steps[-1]["moving"], "latched": steps[-1]["latched"]}
        return res

    n_setting = getattr(ss.settings, NAME, None)
    print(f"[INFO] {NAME} = {n_setting} (None: the code before 147)", flush=True)
    out = scenarios("test-f147-")

    # 1
    a, b = by_t(out["1a"]), by_t(out["1b"])
    check(1, "lone jumps while still (one away and back, two away and back): the anchor and its clock stay, "
             "the red comes at man_down_minutes; a jump when it's due raises nothing, the next fix does",
          fired(out["1a"]) == [(60, "man_down")]
          and all(s["anchor"] == (SPOT[0], SPOT[1], 0, False) for s in out["1a"])
          and (a[20]["count"], a[22]["count"], a[40]["count"], a[42]["count"], a[44]["count"]) == (1, 0, 1, 2, 0)
          and not any(s["moving"] for s in out["1a"]) and a[70]["latched"]
          and fired(out["1b"]) == [(62, "man_down")] and b[60]["alert"] is None
          and all(s["anchor"] == (SPOT[0], SPOT[1], 0, False) for s in out["1b"]),
          f"fired={fired(out['1a'])} counts={[a[t]['count'] for t in (20, 22, 40, 42, 44)]} "
          f"anchor_moved={sorted({s['anchor'] for s in out['1a']} - {(SPOT[0], SPOT[1], 0, False)})} "
          f"jump_when_due: fired={fired(out['1b'])}")

    # 2
    s = by_t(out["2"])
    first_two = [(s[t]["anchor"], s[t]["latched"], s[t]["moving"], s[t]["count"]) for t in (70, 72)]
    check(2, "three fixes in a row away: the first two change nothing; the third re-anchors there, restarts the "
             "clock, clears the latch, marks the person as moving; the next red 60 s after it",
          first_two == [((SPOT[0], SPOT[1], 0, False), True, False, 1), ((SPOT[0], SPOT[1], 0, False), True, False, 2)]
          and (s[74]["anchor"], s[74]["latched"], s[74]["moving"], s[74]["count"]) == ((FAR[0], FAR[1], 74, False), False, True, 0)
          and fired(out["2"]) == [(60, "man_down"), (134, "man_down")],
          f"at 70 and 72={first_two} at 74={(s[74]['anchor'], s[74]['latched'], s[74]['moving'], s[74]['count'])} "
          f"fired={fired(out['2'])}")

    # 3
    s = by_t(out["3"])
    check(3, "a fix within epsilon between away fixes resets the count: two away, one back, then the move needs "
             "three more",
          (s[12]["count"], s[14]["count"], s[18]["count"]) == (2, 0, 2)
          and s[18]["anchor"] == (SPOT[0], SPOT[1], 0, False) and not s[18]["moving"]
          and s[20]["anchor"] == (FAR[0], FAR[1], 20, False) and s[20]["moving"] and fired(out["3"]) == [],
          f"counts at 12, 14, 18={[s[t]['count'] for t in (12, 14, 18)]} anchor at 18={s[18]['anchor']} "
          f"at 20={s[20]['anchor']} moving={s[20]['moving']}")

    # 4
    s = by_t(out["4"])
    check(4, "approximate readings between away fixes neither count nor reset it, and leave the exact anchor alone",
          (s[10]["count"], s[12]["count"], s[14]["count"], s[16]["count"], s[17]["count"]) == (1, 1, 2, 2, 2)
          and all(s[t]["anchor"] == (SPOT[0], SPOT[1], 0, False) for t in (10, 12, 14, 16, 17))
          and s[18]["anchor"] == (FAR[0], FAR[1], 18, False) and s[18]["moving"] and fired(out["4"]) == [],
          f"counts={[s[t]['count'] for t in (10, 12, 14, 16, 17)]} anchor at 17={s[17]['anchor']} at 18={s[18]['anchor']}")

    # 5
    steps = out["5"]
    idx = [i for i in range(len(steps)) if i == 0 or steps[i]["anchor"] != steps[i - 1]["anchor"]]
    gaps = [b - a for a, b in zip(idx, idx[1:])]
    check(5, "walking steadily (1.2 m/s, a fix every 2 s, 3 minutes): re-anchored at least every third fix, "
             "never alerted",
          len(steps) == 90 and gaps and max(gaps) <= 3 and fired(steps) == []
          and stored("test-f147-walker") == [] and steps[-1]["moving"],
          f"fixes={len(steps)} anchors={len(idx)} most fixes between anchors={max(gaps) if gaps else None} "
          f"fired={fired(steps)}")

    # 6
    s, m = by_t(out["6a"]), by_t(out["6b"])
    check(6, "the upgrade: a lone jump during the 30 s doesn't end the run (it keeps confirming from 70) and the red "
             "comes at 30 s; three fixes in a row away end the run as movement",
          fired(out["6a"]) == [(60, "possible_man_down"), (100, "man_down")]
          and s[80]["run"] == (AP1[0], AP1[1], 0, 70, True) and s[80]["anchor"] == (U[0], U[1], 0, False)
          and s[80]["count"] == 1 and not s[80]["moving"] and s[100]["run"] is None and not s[110]["moving"]
          and [m[t]["run"] is not None for t in (80, 82, 84)] == [True, True, False]
          and m[84]["anchor"] == (U_FAR[0], U_FAR[1], 84, False) and m[84]["moving"]
          and fired(out["6b"]) == [(60, "possible_man_down")],
          f"jump: fired={fired(out['6a'])} run at 80={s[80]['run']} anchor at 80={s[80]['anchor']}; "
          f"move: run left at 80, 82, 84={[m[t]['run'] is not None for t in (80, 82, 84)]} "
          f"anchor at 84={m[84]['anchor']} fired={fired(out['6b'])}")

    # 7
    steps = out["7"]
    after = [x for x in steps if x["t"] >= 1000]
    check(7, "after a restart, lone jumps aren't movement: the unresolved alert for the same spot still stops a "
             "repeat, after one /alerts read",
          fired(steps) == [(60, "man_down")] and out["7-stored"] == ["man_down"] and out["7-reads"] == 1
          and not any(x["moving"] for x in after) and after[-1]["latched"],
          f"fired={fired(steps)} stored={out['7-stored']} reads={out['7-reads']} "
          f"moving={any(x['moving'] for x in after)} latched={after[-1]['latched']}")

    # 8: the same inputs with the setting at 1
    had = hasattr(ss.settings, NAME)
    before_value = getattr(ss.settings, NAME, None)
    object.__setattr__(ss.settings, NAME, 1)
    try:
        n1 = summary(scenarios("test-f147-n1-"))
    finally:
        if had:
            object.__setattr__(ss.settings, NAME, before_value)
        else:
            object.__delattr__(ss.settings, NAME)
    if args.print_n1:
        print("TODAY = " + repr(n1), flush=True)
    diff = sorted(k for k in set(n1) | set(TODAY or {}) if (TODAY or {}).get(k) != n1.get(k))
    check(8, "with the setting at 1, the inputs of checks 1-7 give the results of the code before 147",
          TODAY is not None and not diff, f"differs in {diff}" if TODAY is not None else "TODAY not recorded")

    # 9: the setting
    def load_with(value):
        saved = os.environ.pop(NAME, None)
        try:
            if value is not None:
                os.environ[NAME] = value
            return getattr(cs._load(), NAME, "absent")
        except Exception as e:
            return f"{type(e).__name__}: {e}"
        finally:
            os.environ.pop(NAME, None)
            if saved is not None:
                os.environ[NAME] = saved

    def sentence(v):
        return f"ValueError: {NAME} must be a whole number of at least 1, not {v!r}."

    default, ok = load_with(None), {v: load_with(v) for v in ("1", "4")}
    bad = {v: load_with(v) for v in ("0", "-1", "2.5", "three", "")}
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env[NAME] = "0"
    try:
        child = subprocess.run([sys.executable, "-B", "-c", "import config.settings"], cwd=backend_dir, env=env,
                               capture_output=True, text=True, timeout=120)
        child_rc, child_last = child.returncode, (child.stderr.strip().splitlines() or [""])[-1]
    except Exception as e:
        child_rc, child_last = None, f"{type(e).__name__}: {e}"
    check(9, "the setting: 3 by default, 1 and 4 accepted; 0, -1, 2.5, a word or empty stop startup with one "
             "sentence (in _load() and in a fresh process)",
          default == 3 and ok == {"1": 1, "4": 4} and all(bad[v] == sentence(v) for v in bad)
          and child_rc not in (0, None) and child_last == sentence("0"),
          f"default={default} ok={ok} bad={bad} child: exit {child_rc}, last line {child_last!r}")

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
