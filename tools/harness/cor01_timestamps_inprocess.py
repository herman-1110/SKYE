"""In-process checks for COR-01 (Prompt 135): one bad timestamp can no longer
switch off signal-loss man-down for everyone.

  1  /telemetry with a naive timestamp (no time zone) -> 422, nothing written
  2  /telemetry with malformed timestamps -> 422
  3  /telemetry more than 5 minutes in the future -> 422; 2 minutes ahead -> 200
  4  /telemetry with an aware timestamp now, a "Z" one, and one six minutes in
     the past (the simulator's backdated seed) -> 200
  5  the sweep, with a stale good record next to a naive one and a non-string
     one: alerts on the good record, skips the bad ones, logs each once
  6  a second sweep logs neither bad record again (once per person per hour)
     and doesn't re-alert the good one

Requests go through httpx's ASGI transport from a loopback address.

usage (Git Bash, repo root):
  "$py" -B tools/harness/cor01_timestamps_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import asyncio
import contextlib
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

TOKEN = "harness-fake-omada-token-cor01"
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "cor01_timestamps_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-cor01-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": TOKEN,
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "GO2RTC_CONFIG_PATH": os.path.join(run_dir, "go2rtc.yaml"),
        "HARNESS_SEED_STALE": "0",
    })
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    import harness_fakes
    harness_fakes.install_tripwire(run_dir)
    store = harness_fakes.install_fakes(run_dir)
    import harness_seed
    harness_seed.seed(store)

    import httpx
    import main
    from firebase_admin import db
    from repositories.alert_repository import alert_repository
    from services.safety_service import safety_service

    auth = {"Authorization": f"Bearer {TOKEN}"}
    readings = [{"ap_mac": a["mac"], "rssi": -60.0 - 2 * i, "ap_x": a["x_m"], "ap_y": a["y_m"]}
                for i, a in enumerate(C.APS)]
    n = {"i": 0}

    def post(ts):
        n["i"] += 1
        reporter = f"AA:00:00:00:61:{n['i']:02X}"
        body = {"reporter_mac": reporter, "timestamp": ts, "readings": readings,
                "person_id": f"test-cor01-{n['i']}", "person_type": "worker"}

        async def go():
            transport = httpx.ASGITransport(app=main.app, client=("127.0.0.1", 5555))
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                return await c.post("/telemetry", json=body, headers=auth)
        r = asyncio.run(go())
        return r.status_code, db.reference(f"/positions/{reporter.replace(':', '_')}").get() is not None

    now = datetime.now(timezone.utc)

    # 1
    naive = post(now.replace(tzinfo=None).isoformat())
    check(1, "a naive timestamp -> 422, nothing written", naive == (422, False), f"{naive}")

    # 2
    bad = [post(v) for v in ("not-a-time", "2026-13-45T99:00:00+00:00", "1760000000")]
    check(2, "malformed timestamps -> 422", all(b == (422, False) for b in bad), f"{bad}")

    # 3
    far = post((now + timedelta(minutes=10)).isoformat())
    near = post((now + timedelta(minutes=2)).isoformat())
    check(3, "10 minutes ahead -> 422; 2 minutes ahead -> 200",
          far == (422, False) and near == (200, True), f"far={far} near={near}")

    # 4
    good = [post(datetime.now(timezone.utc).isoformat()),
            post(datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
            post((datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat())]
    check(4, "aware now, 'Z', and six minutes in the past -> 200 and written",
          all(g == (200, True) for g in good), f"{good}")

    # 5 and 6: the sweep
    stale = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()

    def rec(pid, ts):
        return {"beacon_mac": pid, "person_id": pid, "person_type": "worker", "x": 1.0, "y": 1.0,
                "zone": "unknown", "timestamp": ts}

    db.reference("/positions").set({
        "test-cor01-good": rec("test-cor01-good", stale),
        "test-cor01-naive": rec("test-cor01-naive", "2026-10-12T02:00:00"),
        "test-cor01-number": rec("test-cor01-number", 1760000000),
    })
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fired = safety_service.check_man_down_stale()
    first = out.getvalue()
    alerts = [a for a in (alert_repository.get_all() or {}).values() if a.get("person_id") == "test-cor01-good"]
    logged = [ln for ln in first.splitlines() if "signal-loss sweep" in ln]
    check(5, "the sweep alerts on the good record and skips both bad ones, logging each once",
          [a.person_id for a in fired] == ["test-cor01-good"] and len(alerts) == 1
          and alerts[0].get("cause") == "signal_loss" and len(logged) == 2
          and any("test-cor01-naive" in ln for ln in logged) and any("test-cor01-number" in ln for ln in logged),
          f"fired={[a.person_id for a in fired]} saved={len(alerts)} logged={len(logged)}")

    out2 = io.StringIO()
    with contextlib.redirect_stdout(out2):
        fired2 = safety_service.check_man_down_stale()
    logged2 = [ln for ln in out2.getvalue().splitlines() if "signal-loss sweep" in ln]
    check(6, "a second sweep logs neither bad record again and doesn't re-alert the good one",
          fired2 == [] and logged2 == [], f"fired={len(fired2)} logged={len(logged2)}")

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
