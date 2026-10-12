"""In-process checks for SEC-01 (Prompt 135): the two ingest routes are fenced
by caller address as well as by the token.

  1  /telemetry from a LAN address (right token, valid body) -> 403 with the
     fixed sentence, nothing written; a host that isn't an IP -> 403 too
  2  /telemetry from 127.0.0.1, 127.0.0.2, ::1 and ::ffff:127.0.0.1 -> 200
  3  /telemetry from loopback with a wrong token -> 401 (the token still counts)
  4  /telemetry/omada with OMADA_INGEST_ALLOWED_IPS unset: any address with the
     right token -> 200; a wrong token -> 401
  5  allowlist set: a listed address -> 200; an unlisted one -> 403 with the
     fixed sentence, also with a wrong token (the source check runs first);
     a listed address with a wrong token -> 401
  6  each rejected address is logged once per 10 minutes, not per request
  7  startup: allowlist unset -> one warning line; set -> none
  8  the setting's parser normalises the list and refuses a bad entry by name

Requests go through httpx's ASGI transport with a chosen client address
(Starlette's TestClient always reports the host "testclient").

usage (Git Bash, repo root):
  "$py" -B tools/harness/sec01_ingest_fence_inprocess.py --backend-dir "$exp/backend"

No server, no port, no network; the real backend/.env is never read.
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402

TOKEN = "harness-fake-omada-token-sec01"
results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


class Collect(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.messages = []

    def emit(self, record):
        try:
            self.messages.append(record.getMessage())
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "sec01_ingest_fence_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_", "GO2RTC_")):
            del os.environ[k]
    os.environ.update({
        "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
        "FIREBASE_RTDB_URL": "https://harness-fake-sec01-default-rtdb.firebaseio.com",
        "GEMINI_API_KEY": "harness-fake-gemini-key",
        "OMADA_ACCESS_TOKEN": TOKEN,
        "LLM_MODEL_NAME": "harness-fake-model",
        "VIGI_DISCOVERY_INTERVAL_S": "0",
        "GO2RTC_CONFIG_PATH": os.path.join(run_dir, "go2rtc.yaml"),
        "GO2RTC_API_URL": "http://127.0.0.1:9",
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
    import middleware.auth_middleware as am
    from config import settings as settings_mod
    from config.settings import settings
    from firebase_admin import db
    from fastapi.testclient import TestClient

    def call(host, path, body, headers=None):
        async def go():
            transport = httpx.ASGITransport(app=main.app, client=(host, 5555))
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                return await c.post(path, json=body, headers=headers or {})
        r = asyncio.run(go())
        try:
            data = r.json()
        except ValueError:
            data = r.text
        return r.status_code, data

    def tel_body(reporter):
        readings = [{"ap_mac": a["mac"], "rssi": -60.0 - 2 * i, "ap_x": a["x_m"], "ap_y": a["y_m"]}
                    for i, a in enumerate(C.APS)]
        return {"reporter_mac": reporter, "timestamp": datetime.now(timezone.utc).isoformat(),
                "readings": readings, "person_id": f"test-sec01-{reporter[-2:]}", "person_type": "worker"}

    def omada_body(token, a=C.APS[0]):
        return {"meta": {"access_token": token, "clientId": "harness", "nbTopic": "telemetry"},
                "reporter": {"name": a["reporter_name"], "mac": C.ap_wire_mac(a), "ipv4": a["ipv4"]},
                "reported": []}

    def position(reporter):
        return db.reference(f"/positions/{reporter.replace(':', '_')}").get()

    def set_allowlist(value):
        object.__setattr__(settings, "OMADA_INGEST_ALLOWED_IPS", value)

    good = {"Authorization": f"Bearer {TOKEN}"}
    bad = {"Authorization": "Bearer not-the-token"}

    # 1
    lan = call("192.168.0.50", "/telemetry", tel_body("AA:00:00:00:51:01"), good)
    named = call("testclient", "/telemetry", tel_body("AA:00:00:00:51:02"), good)
    check(1, "/telemetry from a LAN address or a non-IP host -> 403 with the fixed sentence, nothing written",
          lan[0] == 403 and isinstance(lan[1], dict) and lan[1].get("detail") == am.LOOPBACK_ONLY
          and named[0] == 403 and position("AA:00:00:00:51:01") is None and position("AA:00:00:00:51:02") is None,
          f"lan={lan[0]} testclient={named[0]}")

    # 2
    hosts = {"127.0.0.1": "AA:00:00:00:52:01", "127.0.0.2": "AA:00:00:00:52:02",
             "::1": "AA:00:00:00:52:03", "::ffff:127.0.0.1": "AA:00:00:00:52:04"}
    codes = {h: call(h, "/telemetry", tel_body(mac), good)[0] for h, mac in hosts.items()}
    written = {h: position(mac) is not None for h, mac in hosts.items()}
    check(2, "/telemetry from 127.0.0.1, 127.0.0.2, ::1, ::ffff:127.0.0.1 -> 200 and a position is written",
          all(c == 200 for c in codes.values()) and all(written.values()), f"codes={codes} written={written}")

    # 3
    wrong = call("127.0.0.1", "/telemetry", tel_body("AA:00:00:00:53:01"), bad)
    check(3, "/telemetry from loopback with a wrong token -> 401", wrong[0] == 401, f"status={wrong[0]}")

    # 4
    set_allowlist(())
    open_ok = call("192.168.0.77", "/telemetry/omada", omada_body(TOKEN))
    open_bad = call("192.168.0.77", "/telemetry/omada", omada_body("not-the-token"))
    check(4, "/telemetry/omada, allowlist unset: any address with the right token -> 200; wrong token -> 401",
          open_ok[0] == 200 and open_bad[0] == 401, f"right={open_ok[0]} wrong={open_bad[0]}")

    # 5 and 6
    collect = Collect()
    logging.getLogger("middleware.auth_middleware").addHandler(collect)
    am._rejected_logged.clear()
    set_allowlist(("192.168.0.201", "192.168.0.202"))
    listed = call("192.168.0.201", "/telemetry/omada", omada_body(TOKEN))
    unlisted = call("192.168.0.77", "/telemetry/omada", omada_body(TOKEN))
    unlisted_bad = call("192.168.0.77", "/telemetry/omada", omada_body("not-the-token"))
    listed_bad = call("192.168.0.202", "/telemetry/omada", omada_body("not-the-token"))
    other = call("192.168.0.78", "/telemetry/omada", omada_body(TOKEN))
    check(5, "allowlist set: listed -> 200; unlisted -> 403 (also with a wrong token); listed + wrong token -> 401",
          listed[0] == 200 and unlisted[0] == 403 and isinstance(unlisted[1], dict)
          and unlisted[1].get("detail") == am.SOURCE_NOT_ALLOWED and unlisted_bad[0] == 403
          and listed_bad[0] == 401 and other[0] == 403,
          f"listed={listed[0]} unlisted={unlisted[0]} unlisted+wrong={unlisted_bad[0]} "
          f"listed+wrong={listed_bad[0]} other={other[0]}")
    lines = [m for m in collect.messages if "rejected source" in m]
    check(6, "rejected addresses are logged once each per 10 minutes, not once per request",
          len(lines) == 2 and sum("192.168.0.77" in m for m in lines) == 1
          and sum("192.168.0.78" in m for m in lines) == 1, f"lines={lines}")
    logging.getLogger("middleware.auth_middleware").removeHandler(collect)

    # 7
    root = Collect()
    logging.getLogger().addHandler(root)
    set_allowlist(("192.168.0.201",))
    with TestClient(main.app):
        pass
    warned_set = [m for m in root.messages if "OMADA_INGEST_ALLOWED_IPS is not set" in m]
    root.messages.clear()
    set_allowlist(())
    with TestClient(main.app):
        pass
    warned_unset = [m for m in root.messages if "OMADA_INGEST_ALLOWED_IPS is not set" in m]
    logging.getLogger().removeHandler(root)
    check(7, "startup: allowlist set -> no warning; unset -> exactly one warning line",
          not warned_set and len(warned_unset) == 1, f"set={len(warned_set)} unset={len(warned_unset)}")

    # 8
    parse = settings_mod._ipv4_list
    try:
        parse("OMADA_INGEST_ALLOWED_IPS", "192.168.0.3, banana")
        refused = ""
    except ValueError as e:
        refused = str(e)
    check(8, "parser: ' 192.168.0.3 ,192.168.0.4 ' -> two addresses; '' -> (); a bad entry is refused by name",
          parse("X", " 192.168.0.3 ,192.168.0.4 ") == ("192.168.0.3", "192.168.0.4") and parse("X", "") == ()
          and "OMADA_INGEST_ALLOWED_IPS" in refused and "banana" in refused, f"refused={refused!r}")

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
