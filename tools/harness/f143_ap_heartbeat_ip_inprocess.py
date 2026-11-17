"""In-process checks for Prompt 143, D4.1: the AP heartbeat carries the AP's IP.

The Omada ingest writes reporter.ipv4 into /ap_heartbeats/<MAC> as ip, but only
when it's a dotted IPv4 (Python's ipaddress); otherwise the node has no ip.
mac, name, last_seen and up_since are written as before. Reports go through
omada_ingest_service.ingest() (and once through POST /telemetry/omada), shaped
like a real AP's: reporter {name, mac, hwType, swVersion, swBuild, ipv4, time}.

  1  a placed AP's report with reporter.ipv4: the node is exactly
     {mac, name, last_seen, up_since, ip}
  2  an AP placed nowhere (the "online but not placed" list) gets its ip too
  3  a report without ipv4: no ip, the other four fields as before; an AP
     whose previous report had one loses it
  4  invalid values give no ip, and the ingest still takes the report: out of
     range, words, empty, leading zeros, too short, a CIDR, IPv6, an integer
     (ipaddress would take it), a float, null, true, a list, an object
  5  spaces around a valid address are dropped
  6  up_since and last_seen behave as before with an ip present: a run of
     reports keeps up_since, a silence past AP_SILENT_AFTER_S starts a new run;
     an empty reporter name is still ""
  7  POST /telemetry/omada with the token: 200, and the node has the ip
  8  simulated heartbeats (/telemetry's writer) have no ip

The clock: time.time in omada_ingest_service.

usage (Git Bash, repo root):
  "$py" -B tools/harness/f143_ap_heartbeat_ip_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import json
import os
import sys
import time as _real_time
import types

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

TOKEN = "harness-fake-omada-token-f143"
UNIX0 = 1_790_000_000
UNPLACED_MAC = "AA:BB:CC:14:3A:01"
results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


def report(mac_colons, name="EAP770", ipv4="absent", with_meta=False):
    reporter = {"name": name, "mac": mac_colons.replace(":", "").upper(), "hwType": "2.0",
                "swVersion": "1.4.3", "swBuild": "14057", "time": "1790000000"}
    if ipv4 != "absent":
        reporter["ipv4"] = ipv4
    body = {"reporter": reporter, "reported": []}
    if with_meta:
        body = {"meta": {"access_token": TOKEN, "clientId": "harness", "nbTopic": "telemetry"}, **body}
    return body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "f143_ap_heartbeat_ip_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_", "AP_SILENT", "AP_ALIVE")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-f143ip-default-rtdb.firebaseio.com",
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

    import services.omada_ingest_service as OIS
    from config.settings import settings
    from firebase_admin import db
    from models.telemetry import APRssiReading
    import routes.telemetry_routes as telemetry_routes

    clock = {"t": 0}
    fake_time = types.SimpleNamespace(**{k: getattr(_real_time, k) for k in dir(_real_time) if not k.startswith("__")})
    fake_time.time = lambda: float(UNIX0 + clock["t"])
    OIS.time = fake_time
    svc = OIS.omada_ingest_service
    AP1, AP2, AP3 = (a["mac"] for a in C.APS)

    def node(mac):
        return db.reference(f"/ap_heartbeats/{mac.replace(':', '_')}").get()

    def ingest(body, t):
        clock["t"] = t
        return svc.ingest(body)

    def four(mac, name, t, up):
        return {"mac": mac, "name": name, "last_seen": UNIX0 + t, "up_since": UNIX0 + up}

    # 1
    res1 = ingest(report(AP1, "EAP770", "192.168.0.201"), 10)
    n1 = node(AP1)
    want1 = {**four(AP1, "EAP770", 10, 10), "ip": "192.168.0.201"}
    check(1, "a placed AP's report with reporter.ipv4: the node is {mac, name, last_seen, up_since, ip}",
          n1 == want1 and isinstance(res1, dict), f"node={n1} status={res1.get('status') if isinstance(res1, dict) else res1}")

    # 2
    res2 = ingest(report(UNPLACED_MAC, "EAP660 HD", "192.168.0.50"), 11)
    n2 = node(UNPLACED_MAC)
    check(2, "an AP placed nowhere gets its ip too (the \"online but not placed\" list)",
          n2 == {**four(UNPLACED_MAC, "EAP660 HD", 11, 11), "ip": "192.168.0.50"}
          and isinstance(res2, dict) and res2.get("status") == "online_unregistered",
          f"node={n2} status={res2.get('status') if isinstance(res2, dict) else res2}")

    # 3
    ingest(report(AP2, "EAP660 HD"), 12)
    n3a = node(AP2)
    ingest(report(AP1, "EAP770"), 13)            # AP1 had an ip at t=10
    n3b = node(AP1)
    check(3, "no ipv4: no ip, the other four fields as before; an AP whose last report had one loses it",
          n3a == four(AP2, "EAP660 HD", 12, 12) and n3b == four(AP1, "EAP770", 13, 10),
          f"ap2={n3a} ap1={n3b}")

    # 4
    bad = ["192.168.0.300", "not-an-ip", "", "   ", "192.168.000.050", "192.168.0", "192.168.0.1/24", "fe80::1",
           3232235521, 3232235521.0, None, True, ["192.168.0.1"], {"ip": "192.168.0.1"}]
    wrong = []
    for i, value in enumerate(bad):
        t = 20 + i
        res = ingest(report(AP3, "EAP660 HD", value), t)
        n = node(AP3)
        if n != four(AP3, "EAP660 HD", t, 20) or not isinstance(res, dict) or res.get("status") != "ok":
            wrong.append((repr(value), n, res.get("status") if isinstance(res, dict) else res))
    check(4, f"{len(bad)} invalid ipv4 values: no ip, the other fields written, the report still taken",
          not wrong, f"wrong={wrong}")

    # 5
    ingest(report(AP2, "EAP660 HD", " 192.168.0.202 "), 40)
    n5 = node(AP2)
    check(5, "spaces around a valid address are dropped",
          (n5 or {}).get("ip") == "192.168.0.202", f"node={n5}")

    # 6
    for t in range(41, 46):
        ingest(report(AP2, "EAP660 HD", "192.168.0.202"), t)
    n6a = node(AP2)
    gap = 46 + int(settings.AP_SILENT_AFTER_S) + 1
    ingest(report(AP2, "", "192.168.0.202"), gap)
    n6b = node(AP2)
    check(6, "with an ip present, a run of reports keeps up_since; a silence past AP_SILENT_AFTER_S starts a "
             "new run; an empty reporter name is still \"\"",
          n6a == {**four(AP2, "EAP660 HD", 45, 40), "ip": "192.168.0.202"}
          and n6b == {**four(AP2, "", gap, gap), "ip": "192.168.0.202"},
          f"run={n6a} after the gap={n6b}")

    # 7
    import main
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    clock["t"] = 200
    r7 = client.post("/telemetry/omada", json=report(AP3, "EAP660 HD", "192.168.0.203", with_meta=True))
    n7 = node(AP3)
    check(7, "POST /telemetry/omada with the token: 200, and the node has the ip",
          r7.status_code == 200 and (n7 or {}).get("ip") == "192.168.0.203"
          and {k: v for k, v in (n7 or {}).items() if k != "ip"} == four(AP3, "EAP660 HD", 200, 200),
          f"status={r7.status_code} node={n7}")

    # 8
    telemetry_routes._write_ap_heartbeats([APRssiReading(ap_mac=AP1, rssi=-60.0, ap_x=2.0, ap_y=2.0)])
    n8 = node(AP1)
    check(8, "a simulated heartbeat (/telemetry's writer) has no ip",
          isinstance(n8, dict) and "ip" not in n8 and set(n8) == {"mac", "last_seen"}, f"node={n8}")

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
