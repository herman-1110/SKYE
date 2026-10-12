"""In-process checks for SEC-04 (Prompt 135): the raw Omada dump never prints
the ingest token.

  1  with OMADA_RAW_DUMP_ENABLED on, an AP report is dumped and the output
     holds no token, but "***" where meta.access_token was
  2  the dumped JSON line is the whole report with only the token masked
  3  the caller's report is not modified, and the ingest still accepts it
  4  a report with no meta block is dumped without error

usage (Git Bash, repo root):
  "$py" -B tools/harness/sec04_dump_redaction_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import contextlib
import copy
import io
import json
import os
import sys

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

TOKEN = "harness-fake-omada-token-sec04"
results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


def report(ap, with_meta=True):
    body = {
        "reporter": {"name": ap["reporter_name"], "mac": C.ap_wire_mac(ap), "hwType": ap["hwType"],
                     "swVersion": ap["swVersion"], "swBuild": ap["swBuild"], "ipv4": ap["ipv4"],
                     "time": "1788510357"},
        "reported": [{"mac": C.BEACONS["0001"]["ble_mac"], "deviceClass": ["Minew", "iBeacon"],
                      "rssi": {"avg": -61}, "lastseen": 1788510356,
                      "ibeacon": {"uuid": C.BEACON_UUID_WIRE, "major": C.BEACON_MAJOR, "minor": "0001",
                                  "power": -59}}],
    }
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
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "sec04_dump_redaction_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-sec04-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": TOKEN,
        "OMADA_RAW_DUMP_ENABLED": "true",
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

    from services.omada_ingest_service import omada_ingest_service

    def dump(body):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = omada_ingest_service.ingest(body)
        return out.getvalue(), result

    # 1
    raw = report(C.APS[0])
    original = copy.deepcopy(raw)
    text, result = dump(raw)
    masked = '"access_token":"***"' in text
    check(1, "dump on: the AP report is dumped, with no token in the output and *** in its place",
          "[OMADA] AP REPORT" in text and "Raw JSON" in text and TOKEN not in text and masked,
          f"dumped={'Raw JSON' in text} token_in_output={TOKEN in text} masked={masked}")

    # 2
    lines = [ln for ln in text.splitlines() if ln.startswith("[OMADA] {")]
    dumped = json.loads(lines[0][len("[OMADA] "):]) if lines else {}
    expected = copy.deepcopy(original)
    expected["meta"]["access_token"] = "***"
    check(2, "the dumped JSON is the whole report with only meta.access_token masked",
          len(lines) == 1 and dumped == expected, f"json_lines={len(lines)} equal={dumped == expected}")

    # 3
    check(3, "the caller's report is unchanged and the ingest still accepts it",
          raw == original and isinstance(result, dict) and result.get("status") == "ok",
          f"unchanged={raw == original} status={result.get('status') if isinstance(result, dict) else result}")

    # 4
    bare = report(C.APS[1], with_meta=False)
    text2, result2 = dump(bare)
    check(4, "a report with no meta block is dumped without error",
          "Raw JSON" in text2 and isinstance(result2, dict) and TOKEN not in text2,
          f"status={result2.get('status') if isinstance(result2, dict) else result2}")

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
