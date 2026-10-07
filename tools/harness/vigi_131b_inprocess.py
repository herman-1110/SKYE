"""Prompt 131b in-process checks: camera discovery (VALIDATION 1-6).

  1  a fake WS-Discovery responder: the camera lands in /cctv_heartbeats with
     its MAC, IP and name; two replies for one MAC merge into one entry;
     a non-VIGI ONVIF device is ignored
  2  the ARP fallback parses Windows `arp -a` output (dashed MACs), and a
     reply without the VIGI MAC scope gets its MAC from ARP
  3  no credentials ever reach an unregistered camera: after discovery, a
     liveness round and an OpenAPI sweep, the fake camera saw 0 doAuth
     challenges and 0 logins, and no OpenAPI client exists for it
  4  pruning: an unregistered entry unseen for 10 min goes; a registered
     camera's node and a node without discovered_via (the simulator's) stay
  5  ip_mismatch: set when a registered MAC turns up at another IP, cleared
     at once when the registered IP is edited
  6  POST /cctvs/discover: refused without auth and for a non-admin, 200 with
     results (and no credentials) for an admin
  +  VIGI_DISCOVERY_INTERVAL_S=0: the discovery loop sends nothing

usage (Git Bash, repo root):
  "$py" -B tools/harness/vigi_131b_inprocess.py --backend-dir "$exp/backend"

No server, no port 8000, no LAN traffic: the discovery target is a loopback
unicast responder and the local-address list is patched to 127.0.0.1. The
real backend/.env is never read; settings come from fake values below.
"""
import argparse
import asyncio
import json
import os
import socket
import sys
import threading
import time

sys.dont_write_bytecode = True
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C  # noqa: E402
import vigi_fake_camera as FC  # noqa: E402

TEST_PASSWORD = "harnessfake131b"   # set on purpose: nothing may send it to an unregistered camera
FAKE_ENV = {
    "FIREBASE_KEY_PATH": "./harness-fake-service-account.json",
    "FIREBASE_RTDB_URL": "https://harness-fake-p131b-default-rtdb.firebaseio.com",
    "GEMINI_API_KEY": "harness-fake-gemini-key",
    "OMADA_ACCESS_TOKEN": "harness-fake-omada-token",
    "LLM_MODEL_NAME": "harness-fake-model",
    "VIGI_ALARM_PATH_SECRET": "p131b-INPROC-alarm-secret-0123456789abcdef",
    "VIGI_CAMERA_PASSWORD": TEST_PASSWORD,
    "VIGI_DISCOVERY_INTERVAL_S": "0",
    "HARNESS_FAKE_AUTH": "1",
    "HARNESS_SEED_STALE": "0",
}
ADMIN = {"Authorization": "Bearer harness-token:harness-owner"}
USER = {"Authorization": "Bearer harness-token:harness-user"}
results = []


def check(num, name, ok, detail=""):
    results.append({"check": num, "name": name, "ok": bool(ok), "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] #{num} {name}" + (f" - {detail}" if detail else ""), flush=True)


def probe_match(ip, *, mac_scope=None, name="InSight-S445", hardware="InSight-S445", port=80, types="tdn:NetworkVideoTransmitter tds:Device"):
    scopes = [f"onvif://www.onvif.org/name/{name}", f"onvif://www.onvif.org/hardware/{hardware}",
              "onvif://www.onvif.org/Profile/Streaming", "onvif://www.onvif.org/type/NetworkVideoTransmitter"]
    if mac_scope:
        scopes.append(f"onvif://www.onvif.org/VigiInfoStream/{mac_scope}/443--0--0--0")
    return ('<?xml version="1.0" encoding="UTF-8"?><SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
            '<SOAP-ENV:Header><wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action></SOAP-ENV:Header>'
            '<SOAP-ENV:Body><d:ProbeMatches><d:ProbeMatch><wsa:EndpointReference><wsa:Address>uuid:3fa1fe68-b915-4053-a3e1-000000000000'
            f'</wsa:Address></wsa:EndpointReference><d:Types>{types}</d:Types><d:Scopes>{" ".join(scopes)}</d:Scopes>'
            f'<d:XAddrs>http://{ip}:{port}/onvif/device_service</d:XAddrs><d:MetadataVersion>1</d:MetadataVersion>'
            '</d:ProbeMatch></d:ProbeMatches></SOAP-ENV:Body></SOAP-ENV:Envelope>')


class Responder:
    """Loopback stand-in for 239.255.255.250:3702: answers each probe with the current replies."""
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.addr = self.sock.getsockname()
        self.replies = []
        self.probes = 0
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                data, addr = self.sock.recvfrom(65535)
            except OSError:
                return
            if b"Probe" in data:
                self.probes += 1
                for r in list(self.replies):
                    self.sock.sendto(r.encode(), addr)


ARP_SAMPLE = """
Interface: 192.168.0.5 --- 0x7
  Internet Address      Physical Address      Type
  192.168.0.1           a8-42-a1-00-00-01     dynamic
  192.168.0.101         98-ba-5f-8b-10-03     dynamic
  192.168.0.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static
  239.255.255.250       01-00-5e-7f-ff-fa     static

Interface: 172.25.48.1 --- 0x1f
  Internet Address      Physical Address      Type
  172.25.63.255         ff-ff-ff-ff-ff-ff     static
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True)
    args = ap.parse_args()
    backend_dir = os.path.abspath(args.backend_dir)
    if os.path.isdir(os.path.join(backend_dir, "venv")) or os.path.exists(os.path.join(backend_dir, "serviceAccountKey.json")):
        print("refusing: --backend-dir must be a git-archive export, never the live backend/")
        return 2
    run_dir = C.prepare_run_dir(os.path.join(C.RUNS_DIR, "vigi131b_inprocess"))
    for k in list(os.environ):
        if k.startswith(("VIGI_", "OMADA_", "FIREBASE_", "GEMINI_", "LLM_", "HARNESS_")):
            del os.environ[k]
    os.environ.update(FAKE_ENV)

    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    import harness_fakes
    harness_fakes.install_tripwire(run_dir)
    store = harness_fakes.install_fakes(run_dir)
    import harness_seed
    harness_seed.seed(store)
    from firebase_admin import db, firestore
    firestore.client().collection("users").document("harness-user").set({
        "uid": "harness-user", "email": "harness-user@example.invalid", "display_name": "Harness User",
        "role": "user", "status": "approved", "person_id": "", "created_at": "2026-10-06T00:00:00+00:00",
        "email_verified": True})

    import main  # noqa: F401
    from fastapi.testclient import TestClient
    from models.cctv import CCTV
    from repositories.cctv_repository import cctv_repository
    from services import camera_discovery_service as discovery_mod
    from services.camera_discovery_service import camera_discovery_service as disc
    from services.camera_health_service import camera_health_service as health
    from services.cctv_service import cctv_service
    from services.vigi_openapi_client import openapi_clients
    from utils.arp_utils import parse_arp_output

    responder = Responder()
    disc.target = responder.addr
    disc.local_addresses = lambda: ["127.0.0.1"]

    def node(key):
        return ((db.reference("/cctv_heartbeats").get() or {}).get(key))

    # + discovery off: the loop returns without probing
    asyncio.run(asyncio.wait_for(disc.discovery_loop(), 5))
    check(0, "VIGI_DISCOVERY_INTERVAL_S=0: the loop sends no probe", responder.probes == 0, f"probes={responder.probes}")

    # 1. two replies for one MAC merge; a non-VIGI device is ignored
    responder.replies = [
        probe_match("127.0.0.2", mac_scope="AA-BB-CC-13-1B-02", port=80),
        probe_match("127.0.0.2", mac_scope="AA-BB-CC-13-1B-02", port=2020),
        probe_match("127.0.0.7", name="AXIS-M3045", hardware="M3045-V"),
    ]
    found = disc.discover_once(wait=1.0)
    n2 = node("AA_BB_CC_13_1B_02") or {}
    check(1, "fake responder: camera recorded with MAC, IP, name; two replies -> one entry; non-VIGI ignored",
          [c.mac for c in found] == ["AA:BB:CC:13:1B:02"] and n2.get("mac") == "AA:BB:CC:13:1B:02"
          and n2.get("ip") == "127.0.0.2" and n2.get("device_name") == "InSight-S445"
          and n2.get("discovered_via") == "onvif" and isinstance(n2.get("discovered_at"), int)
          and "last_seen" not in n2,
          f"found={[(c.mac, c.ip, c.discovered_via) for c in found]} node={n2}")

    # 2. ARP parsing, and the ARP fallback when the reply has no VIGI MAC scope
    table = parse_arp_output(ARP_SAMPLE)
    check(2, "ARP: Windows `arp -a` output with dashed MACs; broadcast/multicast skipped",
          table == {"192.168.0.1": "A8:42:A1:00:00:01", "192.168.0.101": "98:BA:5F:8B:10:03"}, f"{table}")
    discovery_mod.arp_lookup = lambda ip, timeout=3.0: {"127.0.0.3": "AA:BB:CC:13:1B:03"}.get(ip)
    responder.replies = [probe_match("127.0.0.3", name="VIGI-C540", hardware="C540")]
    found = disc.discover_once(wait=1.0)
    n3 = node("AA_BB_CC_13_1B_03") or {}
    check(2, "reply without the VIGI MAC scope -> MAC from ARP", [c.mac for c in found] == ["AA:BB:CC:13:1B:03"]
          and n3.get("discovered_via") == "arp+onvif" and n3.get("ip") == "127.0.0.3", f"node={n3}")

    # 3. no credentials to an unregistered camera
    cam_state = FC.FakeCameraState(TEST_PASSWORD, mode="ok")
    cert, key = FC.make_self_signed_cert(run_dir)
    openapi = FC.OpenApiServer("127.0.0.2", cam_state, cert, key)
    rtsp = FC.tcp_listener("127.0.0.2")
    responder.replies = [probe_match("127.0.0.2", mac_scope="AA-BB-CC-13-1B-02")]
    disc.discover_once(wait=1.0)
    live = asyncio.run(health.liveness_once())
    for cam in health._devices().values():            # one OpenAPI sweep, exactly as the loop does it
        health.openapi_check(cam)
    client = TestClient(main.app)
    r = client.post("/cctvs/discover", headers=ADMIN)
    snap = cam_state.snapshot()
    check(3, "unregistered camera: liveness probes it, but 0 doAuth challenges, 0 logins, no OpenAPI client",
          live.get("AA:BB:CC:13:1B:02") is True and isinstance((node("AA_BB_CC_13_1B_02") or {}).get("last_seen"), int)
          and snap["challenges"] == 0 and snap["logins"] == 0 and "ipc:AABBCC131B02:1" not in openapi_clients._clients
          and r.status_code == 200,
          f"liveness={live} fake={snap} clients={list(openapi_clients._clients)}")

    # 6. the discover endpoint
    r_none = client.post("/cctvs/discover")
    r_user = client.post("/cctvs/discover", headers=USER)
    r_admin = client.post("/cctvs/discover", headers=ADMIN)
    body = r_admin.json() if r_admin.status_code == 200 else {}
    text = r_admin.text.lower()
    check(6, "POST /cctvs/discover: refused without auth and for a non-admin; admin gets results, no credentials",
          r_none.status_code in (401, 422) and r_user.status_code == 403 and r_admin.status_code == 200
          and [f["mac"] for f in body.get("found", [])] == ["AA:BB:CC:13:1B:02"]
          and body["found"][0]["registered"] is False and body["found"][0]["ip"] == "127.0.0.2"
          and not any(w in text for w in ("password", "stok", TEST_PASSWORD.lower(), "secret")),
          f"none={r_none.status_code} user={r_user.status_code} admin={r_admin.status_code} found={body.get('found')}")

    # 5. ip_mismatch: register the camera at another IP, then fix the IP
    reg = cctv_service.create(C.BUILDING_ID, C.FLOOR_ID, name="P131b cam", x_pct=0.5, y_pct=0.5,
                              mac="aa-bb-cc-13-1b-02", ip="127.0.0.9")
    disc.discover_once(wait=1.0)
    n_mm = node("AA_BB_CC_13_1B_02") or {}
    set_ok = n_mm.get("ip_mismatch") == "127.0.0.2"
    cctv_service.update(C.BUILDING_ID, C.FLOOR_ID, reg.id, {"ip": "127.0.0.2"})
    n_fixed = node("AA_BB_CC_13_1B_02") or {}
    disc.discover_once(wait=1.0)
    n_again = node("AA_BB_CC_13_1B_02") or {}
    check(5, "ip_mismatch set when a registered MAC is found elsewhere; cleared on saving the new IP and stays clear",
          set_ok and "ip_mismatch" not in n_fixed and "ip_mismatch" not in n_again
          and "device_name" in n_mm and n_mm.get("device_name") == "InSight-S445",
          f"mismatch={n_mm.get('ip_mismatch')} after_edit={n_fixed.get('ip_mismatch')} after_round={n_again.get('ip_mismatch')}")

    # 4. pruning
    old = int(time.time()) - 601
    db.reference("/cctv_heartbeats/AA_BB_CC_13_1B_03").update({"discovered_at": old, "last_seen": old})   # unregistered
    db.reference("/cctv_heartbeats/AA_BB_CC_13_1B_02").update({"discovered_at": old, "last_seen": old})   # registered now
    db.reference("/cctv_heartbeats/A8_57_4E_3C_11_01").set({"mac": "A8:57:4E:3C:11:01", "last_seen": old,
                                                            "device_name": "VIGI C340 (Sim)"})          # simulator-style
    removed = disc.prune()
    check(4, "prune: stale unregistered entry removed; registered camera and simulator-style node kept",
          removed == 1 and node("AA_BB_CC_13_1B_03") is None and node("AA_BB_CC_13_1B_02") is not None
          and node("A8_57_4E_3C_11_01") is not None,
          f"removed={removed} keys={sorted((db.reference('/cctv_heartbeats').get() or {}).keys())}")

    openapi.close()
    rtsp.close()
    loud = [p for p in ("UNIMPLEMENTED.txt", "TRIPWIRE_HIT.txt") if os.path.exists(os.path.join(run_dir, p))]
    check(0, "fakes: nothing unimplemented, no tripwire", not loud, f"{loud}")
    failed = [r for r in results if not r["ok"]]
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump({"passed": len(results) - len(failed), "failed": len(failed), "results": results}, f, indent=1)
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
