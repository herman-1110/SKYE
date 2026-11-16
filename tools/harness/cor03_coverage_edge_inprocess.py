"""In-process checks for COR-03 (Prompt 136, Herman's decision (b)): stillness
seen by only one or two APs raises an amber possible_man_down, which exact
three-AP fixes can upgrade to a red man_down.

  1  exact anchor, then still at the coverage edge (approximate readings) for
     man_down_minutes: one possible_man_down, no man_down
  2  approximate readings only: one possible_man_down (not a red man_down),
     and _last_man_down isn't touched
  3  the upgrade: exact fixes within epsilon for 30 s after the alert raise one
     man_down (clock taken from the run's start), and nothing more after that
  4  movement on return: an exact fix past epsilon cancels the upgrade
  5  the strongest AP changes (Prompt 145, decision (c)): nothing changes until
     the new AP has been the strongest for 30 s, and nothing is raised from
     its readings meanwhile; then a new run, timed from the new AP's first
     reading, and it counts as movement
  6  a flicker of approximate readings during the confirmation doesn't restart
     the run; the man_down still comes 30 s after the first exact fix
  7  the strongest AP keeps flipping, never for 30 s: one run, one
     possible_man_down at the run's own AP, and it isn't movement
  8  a third AP doesn't restart the 30 s (Herman, 17 Nov): after AP1, AP2 and
     AP3 alternate, neither the strongest for 30 s by itself; the change counts
     30 s after the first reading away from AP1, at the latest reading's AP,
     timed from that first reading and with both APs as its spots, and its one
     possible_man_down comes 60 s after that first reading
  9  a change during an upgrade's confirmation ends it only once the new AP has
     held 30 s; an exact fix in between doesn't restart the 30 s
 10  the AP-change hold's default is 120 s
 11  at a 120 s hold, with man_down_minutes 1 as in the live check: a move to
     the other AP counts 120 s after its first reading there, and the new run,
     timed from that reading, is already due, so its possible_man_down comes on
     the same reading

man_down_minutes is patched to 1, the clock is driven by patching
safety_service.utcnow_iso; epsilon and the confirmation time are the defaults
(2.0 m, 30 s), and the AP-change hold is set to 30 s (MAN_DOWN_AP_CHANGE_HOLD_S),
the hold these checks were written for, except in 11. Approximate x/y is the
strongest AP's coordinate, as the proximity fallback writes it. On 2975863
every check fails. On 794261a, where a change of strongest AP started a new run
at once, checks 5, 7, 8, 9, 10 and 11 fail. On a886862, where a third AP
restarted the 30 s and the hold's default was 30 s, checks 8 and 10 fail.

usage (Git Bash, repo root):
  "$py" -B tools/harness/cor03_coverage_edge_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

BASE_T = datetime(2026, 10, 20, 2, 0, 0, tzinfo=timezone.utc)
AP1 = (2.0, 2.0)
AP2 = (14.0, 2.0)
AP3 = (8.0, 14.0)
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "cor03_coverage_edge_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "MAN_DOWN_",
                         "AP_SILENT", "AP_ALIVE", "COLLISION_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-cor03-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "GO2RTC_CONFIG_PATH": os.path.join(run_dir, "go2rtc.yaml"),
        "HARNESS_SEED_STALE": "0",
        "MAN_DOWN_AP_CHANGE_HOLD_S": "30",
    })
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    import harness_fakes
    harness_fakes.install_tripwire(run_dir)
    harness_fakes.install_fakes(run_dir)

    import services.safety_service as ss
    from models.position import PositionRecord
    from models.safety_settings import SafetySettings
    from repositories.alert_repository import alert_repository

    svc = ss.safety_service
    svc._get_settings = lambda: SafetySettings(man_down_minutes=1, collision_distance_m=2.0)
    clock = {"t": 0.0}
    ss.utcnow_iso = lambda: (BASE_T + timedelta(seconds=clock["t"])).isoformat()

    def at(t, pid, xy, approx):
        clock["t"] = t
        rec = PositionRecord(beacon_mac=pid, person_id=pid, person_type="worker", x=xy[0], y=xy[1],
                             zone="unknown" if approx else "Z", timestamp=ss.utcnow_iso(), is_approximate=approx)
        a = svc.check_man_down(rec)
        return (int(t), a.alert_type, a.approximate) if a else None

    def exact(t, pid, xy):
        return at(t, pid, xy, False)

    def approx(t, pid, xy=AP1):
        return at(t, pid, xy, True)

    def saved(pid):
        return [(a["alert_type"], bool(a.get("approximate")), a.get("cause"))
                for a in sorted((a for a in alert_repository.get_all().values() if a.get("person_id") == pid),
                                key=lambda a: a["timestamp"])]

    def fired(events):
        return [e for e in events if e is not None]

    def iso(t):
        return (BASE_T + timedelta(seconds=t)).isoformat()

    def run_of(pid):
        """(x, y, started_at, confirming_since, seen moving) of pid's run."""
        r = getattr(ss, "_approx_runs", {}).get(pid)   # none before 136
        moving = pid in getattr(ss, "_seen_moving", set())
        return (r.x, r.y, r.started_at, r.confirming_since, moving) if r else None

    def spots_of(pid):
        r = getattr(ss, "_approx_runs", {}).get(pid)
        return list(getattr(r, "spots", None) or []) if r else None   # none before a886862

    def anchors(pid):
        return [(a.get("anchor_x"), a.get("anchor_y"))
                for a in sorted((a for a in alert_repository.get_all().values() if a.get("person_id") == pid),
                                key=lambda a: a["timestamp"])]

    # 1: exact anchor, then approximate stillness at the coverage edge
    A = "test-cor03-edge"
    ev = [exact(0, A, (5.0, 5.0)), exact(10, A, (5.1, 5.0))] + [approx(t, A) for t in range(20, 101, 10)]
    check(1, "exact anchor, then approximate stillness: one possible_man_down, no man_down",
          fired(ev) == [(80, "possible_man_down", True)]
          and saved(A) == [("possible_man_down", True, "stillness")],
          f"fired={fired(ev)} saved={saved(A)}")

    # 2: approximate only
    B = "test-cor03-approx"
    ev = [approx(t, B) for t in range(0, 91, 10)]
    check(2, "approximate only: one possible_man_down; _last_man_down untouched",
          fired(ev) == [(60, "possible_man_down", True)] and B not in ss._last_man_down,
          f"fired={fired(ev)} last_man_down={ss._last_man_down.get(B)}")

    # 3: B's upgrade: 30 s of exact stillness after the alert
    ev = [exact(100, B, (2.5, 2.5)), exact(115, B, (2.6, 2.5)), exact(131, B, (2.5, 2.6)), exact(160, B, (2.5, 2.5))]
    check(3, "upgrade: exact fixes within epsilon for 30 s -> one man_down, then nothing",
          fired(ev) == [(131, "man_down", False)]
          and saved(B) == [("possible_man_down", True, "stillness"), ("man_down", False, "stillness")],
          f"fired={fired(ev)} saved={saved(B)}")

    # 4: movement on return
    M = "test-cor03-moved"
    ev = [approx(t, M) for t in range(0, 71, 10)]
    ev += [exact(80, M, (2.5, 2.5)), exact(90, M, (8.0, 8.0)), exact(125, M, (8.1, 8.0))]
    check(4, "movement on return: an exact fix past epsilon cancels the upgrade",
          fired(ev) == [(60, "possible_man_down", True)] and saved(M) == [("possible_man_down", True, "stillness")],
          f"fired={fired(ev)} saved={saved(M)}")

    # 5: the strongest AP changes. AP1's run is due at 60, but AP2's readings
    # raise nothing; AP2 has held 29 s at 84 and 30 s at 85.
    N = "test-cor03-newrun"
    ev = [approx(t, N, AP1) for t in range(0, 51, 10)] + [approx(t, N, AP2) for t in (55, 65, 75, 84)]
    at84 = run_of(N)
    ev.append(approx(85, N, AP2))
    at85 = run_of(N)
    ev += [approx(t, N, AP2) for t in range(95, 116, 10)]
    check(5, "the strongest AP changes: counted once the new AP has held 30 s, then a new run "
          "timed from the new AP's first reading, alerting 60 s after it",
          at84 == (AP1[0], AP1[1], iso(0), None, False) and at85 == (AP2[0], AP2[1], iso(55), None, True)
          and fired(ev) == [(115, "possible_man_down", True)],
          f"run at 84={at84} at 85={at85} fired={fired(ev)}")

    # 6: flicker during the confirmation
    F = "test-cor03-flicker"
    ev = [approx(t, F) for t in range(0, 61, 10)]
    ev += [exact(70, F, (2.5, 2.5)), approx(75, F), exact(80, F, (2.6, 2.5)), approx(85, F),
           approx(95, F), exact(101, F, (2.5, 2.4))]
    check(6, "approximate readings during the confirmation don't restart the run",
          fired(ev) == [(60, "possible_man_down", True), (101, "man_down", False)],
          f"fired={fired(ev)}")

    # 7: the strongest AP keeps flipping. A reading every 5 s; each stay is
    # 1-5 readings (the longest from 30 to 50), never 30 s.
    K = "test-cor03-flipping"
    ev, t, xy, i, stays = [], 0, AP1, 0, (1, 4, 1, 5, 2, 3)
    while t <= 150:
        for _ in range(stays[i % len(stays)]):
            if t <= 150:
                ev.append(approx(t, K, xy))
            t += 5
        xy, i = (AP2 if xy == AP1 else AP1), i + 1
    check(7, "the strongest AP keeps flipping, never for 30 s: one run, one possible_man_down at its "
          "own AP, not movement",
          fired(ev) == [(60, "possible_man_down", True)] and run_of(K) == (AP1[0], AP1[1], iso(0), None, False)
          and [(a.get("anchor_x"), a.get("anchor_y")) for a in alert_repository.get_all().values()
               if a.get("person_id") == K] == [AP1],
          f"fired={fired(ev)} run={run_of(K)} saved={saved(K)}")

    # 8: a third AP doesn't restart the 30 s. After AP1, AP2 and AP3 alternate
    # every 5 s from 55: away from AP1 for 29 s at 84 (AP2's reading) and 30 s
    # at 85 (AP3's), when a new run starts at AP3, timed from 55. Then AP3's
    # readings are its own and AP2's a pending change each time; the amber
    # comes at 115, AP3's reading 60 s after 55.
    T3 = "test-cor03-third"
    ev = [approx(t, T3, AP1) for t in range(0, 51, 10)]
    ev += [approx(t, T3, xy) for t, xy in ((55, AP2), (60, AP3), (65, AP2), (70, AP3), (75, AP2), (80, AP3),
                                           (84, AP2))]
    at84 = run_of(T3)
    ev.append(approx(85, T3, AP3))
    at85, spots85 = run_of(T3), spots_of(T3)
    ev += [approx(t, T3, AP2 if t // 5 % 2 == 0 else AP3) for t in range(90, 176, 5)]
    check(8, "a third AP doesn't restart the 30 s: with AP2 and AP3 alternating after AP1, the change counts "
          "30 s after the first reading away, at the latest AP, timed from that reading, both APs its spots; "
          "one amber 60 s after it",
          at84 == (AP1[0], AP1[1], iso(0), None, False) and at85 == (AP3[0], AP3[1], iso(55), None, True)
          and spots85 == [AP3, AP2] and fired(ev) == [(115, "possible_man_down", True)] and anchors(T3) == [AP3],
          f"run at 84={at84} at 85={at85} spots at 85={spots85} fired={fired(ev)} anchors={anchors(T3)}")

    # 9: a change during an upgrade's confirmation: the amber at 60, the first
    # exact fix at 70, AP2 from 75 (held 29 s at 104, 30 s at 105), one exact
    # fix within epsilon at 90, too early to confirm the upgrade
    U = "test-cor03-upgrade-move"
    ev = [approx(t, U) for t in range(0, 61, 10)]
    ev += [exact(70, U, (2.5, 2.5)), approx(75, U, AP2), approx(85, U, AP2), exact(90, U, (2.6, 2.5)),
           approx(95, U, AP2), approx(104, U, AP2)]
    at104 = run_of(U)
    ev.append(approx(105, U, AP2))
    at105 = run_of(U)
    check(9, "a change during the upgrade's confirmation ends it only once the new AP has held 30 s; an "
          "exact fix in between doesn't restart the 30 s",
          at104 == (AP1[0], AP1[1], iso(0), iso(70), False) and at105 == (AP2[0], AP2[1], iso(75), None, True)
          and fired(ev) == [(60, "possible_man_down", True)],
          f"run at 104={at104} at 105={at105} fired={fired(ev)}")

    # 10: the hold's default, read with MAN_DOWN_AP_CHANGE_HOLD_S unset
    import config.settings as cs
    held = os.environ.pop("MAN_DOWN_AP_CHANGE_HOLD_S", None)
    try:
        default_hold = getattr(cs._load(), "MAN_DOWN_AP_CHANGE_HOLD_S", None)
    except Exception as e:
        default_hold = f"{type(e).__name__}: {e}"
    finally:
        if held is not None:
            os.environ["MAN_DOWN_AP_CHANGE_HOLD_S"] = held
    check(10, "the AP-change hold's default is 120 s", default_hold == 120.0, f"default={default_hold}")

    # 11: at a 120 s hold. AP1 from 0, its amber at 60; AP2 from 155, away
    # from AP1 for 119 s at 274 and 120 s at 275, when the new run starts at
    # AP2, timed from 155 and so already due
    settings = cs.settings
    hold_before = getattr(settings, "MAN_DOWN_AP_CHANGE_HOLD_S", None)
    object.__setattr__(settings, "MAN_DOWN_AP_CHANGE_HOLD_S", 120.0)
    try:
        L = "test-cor03-hold-120"
        ev = [approx(t, L, AP1) for t in range(0, 151, 10)] + [approx(t, L, AP2) for t in range(155, 266, 10)]
        ev.append(approx(274, L, AP2))
        at274 = run_of(L)
        ev.append(approx(275, L, AP2))
        at275 = run_of(L)
        ev += [approx(t, L, AP2) for t in range(285, 346, 10)]
    finally:
        object.__setattr__(settings, "MAN_DOWN_AP_CHANGE_HOLD_S", hold_before)
    check(11, "at a 120 s hold: a move to the other AP counts 120 s after its first reading there, and the "
          "new run's amber comes on that same reading",
          fired(ev) == [(60, "possible_man_down", True), (275, "possible_man_down", True)]
          and at274 == (AP1[0], AP1[1], iso(0), None, False) and at275 == (AP2[0], AP2[1], iso(155), None, True)
          and anchors(L) == [AP1, AP2],
          f"fired={fired(ev)} run at 274={at274} at 275={at275} anchors={anchors(L)}")

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
