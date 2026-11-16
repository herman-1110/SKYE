"""In-process checks for Prompt 145, D3: a backend restart doesn't repeat a
stillness alert for someone who hasn't moved.

A "restart" clears every piece of in-memory state check_man_down() keeps;
/alerts (the fake RTDB) survives, as it does on real Firebase. Each case
raises its alert through the real code first, so the alert carries whatever
the code stores, then restarts and feeds the same person again.
man_down_minutes is 1; the clock is safety_service.utcnow_iso.

   1  new stillness alerts carry floor_id and their anchor: the exact anchor
      for a red man_down, the run's anchor (the AP) for a possible_man_down
   2  an unresolved stillness alert at the same spot: no new alert after the
      restart, and the latch (_still_alerted) is set
   3  the same, but acknowledged: no new alert
   4  a resolved alert: a new alert
   5  the person moved after the restart and stopped somewhere new: a new alert
   6  the person moved, then came back to the old spot: a new alert
   7  an alert without an anchor (raised before 145): a new alert
   8  the same spot on another floor: a new alert
   9  possible_man_down at the same AP: none, and the run is latched
  10  the upgrade to a red man_down, both raised before the restart: neither
      repeats, and the run ends
  11  only the amber raised before the restart: the amber doesn't repeat, but
      the upgrade's red is new and is raised
  12  /alerts reads after the restart: one per alert that came due (two for an
      amber and its red), none once the person had moved, and none again
      after a match or a raise
  13  the age limit (MAN_DOWN_RESTART_MATCH_H, 12): an alert 12 h 2 min old
      when the stillness comes due again doesn't count (a new alert), one
      11 h 56 min old does (none), and one whose timestamp has no time zone
      doesn't (a new alert)
  14  flipping between two APs across the restart, never for 30 s, the first
      reading after it at the other AP: no new amber (the match takes any AP
      the run has had as the strongest), not movement, one read
  15  a far AP first after the restart (one reading), then the alert's AP: no
      new amber, not movement, one read
  16  the same before exact fixes (one reading at each of two APs, then exact
      fixes at the red alert's spot): no new red, one read
  17  a real move after the restart: the alert's AP for 40 s, then the other
      AP: a new amber there, 60 s after its first reading, with no read
   0  the fakes: nothing unimplemented, no tripwire

On the base (9f28798) every restart repeats the alert and nothing reads
/alerts: checks 1, 2, 3, 9, 10, 11, 12 and 13-16 fail; 4-8 and 17, which
expect a new alert, pass there too. On 794261a (145's first build, where a
change of strongest AP counted as movement at once and the match had no age
limit), checks 13-16 fail.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f145_stillness_restart_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

BASE_T = datetime(2026, 11, 16, 2, 0, 0, tzinfo=timezone.utc)
SPOT = (5.0, 5.0)
JITTER = (5.3, 5.1)       # 0.32 m from SPOT: the same spot, read again
FAR = (12.0, 5.0)         # 7 m away: past the 2 m epsilon
AP1 = (2.0, 2.0)          # an approximate reading's x/y is the strongest AP's own
AP2 = (14.0, 2.0)         # the other AP, 12 m away
UPGRADE = [(2.5, 2.5), (2.6, 2.5), (2.5, 2.6)]
OTHER_FLOOR = "test-f145-other-floor"
results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f145_stillness_restart_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f145still-default-rtdb.firebaseio.com",
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

    # Count and time the code's /alerts reads; the test's own reads below go
    # through db.reference, so they aren't counted.
    reads = {"n": 0, "ms": [], "size": 0}
    real_get_all = alert_repository.get_all

    def counting_get_all():
        started = time.perf_counter()
        out = real_get_all()
        reads["ms"].append((time.perf_counter() - started) * 1000)
        reads["size"] = len(out or {})
        reads["n"] += 1
        return out
    alert_repository.get_all = counting_get_all

    def at(t, pid, xy, approx=False, floor=FLOOR):
        clock["t"] = t
        rec = PositionRecord(beacon_mac=pid, person_id=pid, person_type="worker", x=xy[0], y=xy[1],
                             zone="unknown" if approx else "Z", timestamp=ss.utcnow_iso(),
                             is_approximate=approx, floor_id=floor, building_id=C.BUILDING_ID)
        a = svc.check_man_down(rec)
        return (int(t), a.alert_type) if a else None

    def still(pid, t0, t1, xy, approx=False, floor=FLOOR, step=10):
        return [e for e in (at(t, pid, xy, approx, floor) for t in range(t0, t1 + 1, step)) if e]

    def stored(pid):
        alerts = (db.reference("/alerts").get() or {}).values()
        return sorted((a for a in alerts if a.get("person_id") == pid), key=lambda a: a["timestamp"])

    def kinds(pid):
        return [a["alert_type"] for a in stored(pid)]

    def anchor(a):
        return (a.get("floor_id"), a.get("anchor_x"), a.get("anchor_y"))

    def restart():
        for name in ("_stale_alerted", "_last_man_down", "_still_alerted", "_man_down_tracker",
                     "_approx_runs", "_last_fresh_mono", "_held_logged", "_seen_moving"):
            if hasattr(ss, name):
                getattr(ss, name).clear()
        reads["n"] = 0

    def red_before(pid, xy=SPOT, floor=FLOOR):
        return still(pid, 0, 70, xy, floor=floor)

    def amber_before(pid):
        return still(pid, 0, 70, AP1, approx=True)

    def upgrade(pid, t0):
        return [e for e in (at(t0 + dt, pid, xy) for dt, xy in zip((0, 15, 31), UPGRADE)) if e]

    def flip(pid, t0, t1, first, other, stays=(1, 4, 1, 5, 2, 3), step=5):
        """Approximate readings every step s from t0 to t1, the strongest AP
        alternating between first and other, each stay that many readings:
        never 30 s."""
        out, t, xy, i = [], t0, first, 0
        while t <= t1:
            for _ in range(stays[i % len(stays)]):
                if t <= t1:
                    e = at(t, pid, xy, approx=True)
                    if e:
                        out.append(e)
                t += step
            xy, i = (other if xy == first else first), i + 1
        return out

    def moving(pid):
        return pid in getattr(ss, "_seen_moving", set())   # none before 145

    n_reads = {}

    # 2 (and 1): an unresolved red at SPOT; restart; still at the same spot
    P1 = "test-f145-same"
    p1_before = red_before(P1)
    p1_alert = stored(P1)[0] if stored(P1) else {}
    restart()
    p1_after = still(P1, 1000, 1400, JITTER)     # due at 1060, then 34 more readings
    n_reads[P1] = reads["n"]
    check(2, "an unresolved stillness alert at the same spot: no new alert, the latch is set",
          p1_before == [(60, "man_down")] and p1_after == [] and kinds(P1) == ["man_down"]
          and P1 in ss._still_alerted,
          f"before={p1_before} after={p1_after} saved={kinds(P1)} latched={P1 in ss._still_alerted}")

    # 9 (and 1): an amber at AP1; restart; approximate at AP1 again
    P8 = "test-f145-amber"
    p8_before = amber_before(P8)
    p8_alert = stored(P8)[0] if stored(P8) else {}
    restart()
    p8_after = still(P8, 1000, 1400, AP1, approx=True)
    n_reads[P8] = reads["n"]
    run = ss._approx_runs.get(P8)
    check(9, "possible_man_down at the same AP: none after the restart, and the run is latched",
          p8_before == [(60, "possible_man_down")] and p8_after == [] and kinds(P8) == ["possible_man_down"]
          and run is not None and run.alerted,
          f"before={p8_before} after={p8_after} saved={kinds(P8)} run_alerted={getattr(run, 'alerted', None)}")

    # 3: acknowledged, unresolved
    P2 = "test-f145-acked"
    red_before(P2)
    a2 = stored(P2)[0]
    db.reference(f"/alerts/{a2['alert_id']}").update({
        "acknowledged_at": "2026-11-16T02:02:00+00:00", "acknowledged_by": "Harness Admin",
        "acknowledged_by_uid": "harness-admin"})
    restart()
    p2_after = still(P2, 1000, 1100, JITTER)
    n_reads[P2] = reads["n"]
    check(3, "the same, but acknowledged: no new alert",
          p2_after == [] and kinds(P2) == ["man_down"], f"after={p2_after} saved={kinds(P2)}")

    # 4: resolved
    P3 = "test-f145-resolved"
    red_before(P3)
    db.reference(f"/alerts/{stored(P3)[0]['alert_id']}").update({"resolved": True})
    restart()
    p3_after = still(P3, 1000, 1400, JITTER)     # raised at 1060, then 34 more readings
    n_reads[P3] = reads["n"]
    check(4, "a resolved alert: a new alert",
          p3_after == [(1060, "man_down")] and kinds(P3) == ["man_down", "man_down"],
          f"after={p3_after} saved={kinds(P3)}")

    # 5: moved after the restart, stopped somewhere new
    P4 = "test-f145-moved"
    red_before(P4)
    restart()
    p4_after = [e for e in (at(1000, P4, SPOT), at(1010, P4, FAR)) if e] + still(P4, 1020, 1100, FAR)
    n_reads[P4] = reads["n"]
    new4 = stored(P4)[-1]
    check(5, "moved after the restart and stopped somewhere new: a new alert",
          p4_after == [(1070, "man_down")] and kinds(P4) == ["man_down", "man_down"],
          f"after={p4_after} saved={kinds(P4)}")

    # 6: moved, then came back to the old spot
    P5 = "test-f145-back"
    red_before(P5)
    restart()
    p5_after = [e for e in (at(1000, P5, SPOT), at(1010, P5, FAR), at(1020, P5, SPOT)) if e] \
        + still(P5, 1030, 1100, SPOT)
    n_reads[P5] = reads["n"]
    check(6, "moved, then came back to the old spot: a new alert",
          p5_after == [(1080, "man_down")] and kinds(P5) == ["man_down", "man_down"],
          f"after={p5_after} saved={kinds(P5)}")

    # 7: an unresolved stillness man_down written before 145: no floor, no anchor
    P6 = "test-f145-old"
    db.reference("/alerts/test-f145-old-alert").set({
        "alert_id": "test-f145-old-alert", "alert_type": "man_down", "person_id": P6, "zone": "Z",
        "timestamp": BASE_T.isoformat(), "resolved": False, "approximate": False, "cause": "stillness"})
    restart()
    p6_after = still(P6, 1000, 1100, SPOT)
    n_reads[P6] = reads["n"]
    check(7, "an alert without an anchor (raised before 145): a new alert",
          p6_after == [(1060, "man_down")] and kinds(P6) == ["man_down", "man_down"],
          f"after={p6_after} saved={kinds(P6)}")

    # 8: the same coordinates on another floor
    P7 = "test-f145-floor"
    red_before(P7)
    restart()
    p7_after = still(P7, 1000, 1100, SPOT, floor=OTHER_FLOOR)
    n_reads[P7] = reads["n"]
    new7 = stored(P7)[-1]
    check(8, "the same spot on another floor: a new alert",
          p7_after == [(1060, "man_down")] and kinds(P7) == ["man_down", "man_down"],
          f"after={p7_after} saved={kinds(P7)}")

    # 10: amber, then the upgrade's red, both before the restart
    P9 = "test-f145-upgrade"
    p9_before = still(P9, 0, 60, AP1, approx=True) + upgrade(P9, 70)
    restart()
    p9_after = still(P9, 1000, 1060, AP1, approx=True) + upgrade(P9, 1070) \
        + still(P9, 1110, 1200, UPGRADE[0])
    n_reads[P9] = reads["n"]
    check(10, "the upgrade, amber and red both raised before the restart: neither repeats, the run ends",
          p9_before == [(60, "possible_man_down"), (101, "man_down")] and p9_after == []
          and kinds(P9) == ["possible_man_down", "man_down"]
          and P9 not in ss._approx_runs and P9 in ss._still_alerted,
          f"before={p9_before} after={p9_after} saved={kinds(P9)} run_left={P9 in ss._approx_runs}")

    # 11: only the amber before the restart
    P10 = "test-f145-amber-only"
    still(P10, 0, 60, AP1, approx=True)
    restart()
    p10_after = still(P10, 1000, 1060, AP1, approx=True) + upgrade(P10, 1070)
    n_reads[P10] = reads["n"]
    check(11, "only the amber before the restart: it doesn't repeat, and the upgrade's red is raised",
          p10_after == [(1101, "man_down")] and kinds(P10) == ["possible_man_down", "man_down"],
          f"after={p10_after} saved={kinds(P10)}")

    # 1: what the code stored, on the alerts raised above
    check(1, "new stillness alerts carry floor_id and their anchor (red: the exact anchor; amber: the AP)",
          anchor(p1_alert) == (FLOOR, SPOT[0], SPOT[1]) and anchor(p8_alert) == (FLOOR, AP1[0], AP1[1])
          and anchor(new4) == (FLOOR, FAR[0], FAR[1]) and anchor(new7) == (OTHER_FLOOR, SPOT[0], SPOT[1]),
          f"red={anchor(p1_alert)} amber={anchor(p8_alert)} moved={anchor(new4)} other_floor={anchor(new7)}")

    # 12: read counts after each restart. P1, P3 and P8 ran on to t=1400 (34
    # readings after the one that came due), so a second read would show here.
    want = {P1: 1, P2: 1, P3: 1, P4: 0, P5: 0, P6: 1, P7: 1, P8: 1, P9: 2, P10: 2}
    check(12, "one /alerts read per alert that came due after a restart (none once the person moved, none again after)",
          n_reads == want, f"reads={n_reads} want={want}")
    if reads["ms"]:
        print(f"[INFO] the fake's /alerts read: {len(reads['ms'])} reads, max {max(reads['ms']):.2f} ms, "
              f"/alerts holding {reads['size']} alerts at the last one (in-process, not the real RTDB)", flush=True)

    # 13: the age limit. Each red is raised at 60; after the restart the
    # stillness comes due again at T + 60, when the alert is T s old.
    P11, P12, P13 = "test-f145-older-12h", "test-f145-within-12h", "test-f145-naive-ts"
    aged = {}
    for pid, t_after in ((P11, 43320), (P12, 42960)):   # 12 h 2 min, 11 h 56 min
        red_before(pid)
        restart()
        aged[pid] = (still(pid, t_after, t_after + 100, JITTER), reads["n"])
    red_before(P13)
    db.reference(f"/alerts/{stored(P13)[0]['alert_id']}").update({"timestamp": "2026-11-16T02:01:00"})
    restart()
    aged[P13] = (still(P13, 1000, 1100, JITTER), reads["n"])
    check(13, "the age limit: 12 h 2 min old -> a new alert; 11 h 56 min -> none; a timestamp without a "
          "time zone -> a new alert; one read each",
          aged == {P11: ([(43380, "man_down")], 1), P12: ([], 1), P13: ([(1060, "man_down")], 1)}
          and [len(kinds(p)) for p in (P11, P12, P13)] == [2, 1, 2],
          f"{aged} saved={[kinds(p) for p in (P11, P12, P13)]}")

    # 14: flipping between AP1 and AP2 across the restart. After it the first
    # reading is AP2's, so the run is AP2's and AP1 is where it flips to.
    P14 = "test-f145-flip"
    p14_before = flip(P14, 0, 120, AP1, AP2)
    p14_alert = stored(P14)[0] if stored(P14) else {}
    restart()
    p14_after = flip(P14, 1000, 1200, AP2, AP1)
    run14 = ss._approx_runs.get(P14)
    run14 = (run14.x, run14.y, run14.alerted) if run14 else None
    check(14, "flipping between two APs, the first reading after the restart at the other AP: no new amber, "
          "not movement, one read",
          p14_before == [(60, "possible_man_down")] and anchor(p14_alert) == (FLOOR, AP1[0], AP1[1])
          and p14_after == [] and kinds(P14) == ["possible_man_down"] and reads["n"] == 1
          and run14 == (AP2[0], AP2[1], True) and not moving(P14),
          f"before={p14_before} alert={anchor(p14_alert)} after={p14_after} saved={kinds(P14)} "
          f"reads={reads['n']} run={run14} moving={moving(P14)}")

    # 15: a far AP first: the first reading after the restart is AP2's (one AP
    # in the first flush), then AP1's, where the amber was raised
    P15 = "test-f145-far-first"
    amber_before(P15)
    restart()
    p15_after = [e for e in [at(1000, P15, AP2, approx=True)] if e] + still(P15, 1002, 1102, AP1, approx=True)
    check(15, "a far AP first after the restart, then the alert's AP: no new amber, not movement, one read",
          p15_after == [] and kinds(P15) == ["possible_man_down"] and reads["n"] == 1 and not moving(P15),
          f"after={p15_after} saved={kinds(P15)} reads={reads['n']} moving={moving(P15)}")

    # 16: the same before exact fixes: one approximate reading at each of two
    # APs, then exact fixes at the red alert's spot
    P16 = "test-f145-far-first-red"
    red_before(P16)
    restart()
    p16_after = [e for e in (at(1000, P16, AP2, approx=True), at(1001, P16, AP1, approx=True)) if e] \
        + still(P16, 1002, 1102, JITTER)
    check(16, "the same before exact fixes (two APs, then the red alert's spot): no new red, one read",
          p16_after == [] and kinds(P16) == ["man_down"] and reads["n"] == 1,
          f"after={p16_after} saved={kinds(P16)} reads={reads['n']}")

    # 17: a real move after the restart: AP1, the alert's, for 40 s, then AP2,
    # held 30 s at 1075
    P17 = "test-f145-real-move"
    amber_before(P17)
    restart()
    p17_after = still(P17, 1000, 1040, AP1, approx=True) + still(P17, 1045, 1145, AP2, approx=True)
    check(17, "a real move after the restart (AP1 for 40 s, then AP2): a new amber at AP2, 60 s after its "
          "first reading, with no read",
          p17_after == [(1105, "possible_man_down")] and kinds(P17) == ["possible_man_down", "possible_man_down"]
          and reads["n"] == 0,
          f"after={p17_after} saved={kinds(P17)} reads={reads['n']}")

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
