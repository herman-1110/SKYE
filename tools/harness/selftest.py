"""Self-tests for the harness itself (no backend server, no real network).

usage: python -B selftest.py [scratch_dir]   (default tools/harness/runs/selftest)

1. tripwire: each outbound path is exercised in its own subprocess, wrapped
   in `try/except Exception: pass`, and must still hard-exit with code 99 and
   write TRIPWIRE_HIT.txt. Every subprocess has HTTP(S)_PROXY/grpc_proxy set
   to 127.0.0.1:9 (closed port) so a tripwire that failed to fire still could
   not reach the internet via any HTTP/gRPC stack.
2. fakes: RTDB + Firestore semantics used by the app, and loud NotImplementedError.
ASCII console output only.
"""
import os
import subprocess
import sys
import textwrap

sys.dont_write_bytecode = True
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))

PRE = textwrap.dedent("""
    import sys, os
    sys.dont_write_bytecode = True
    sys.path.insert(0, {hd!r})
    import harness_fakes as HF
    HF.install_tripwire({rd!r})
""")

CASES = {
    "requests": """
import requests
try:
    requests.get("https://selftest.firebaseio.com/x.json", timeout=2)
except Exception:
    pass
""",
    "google_auth_authorized_session": """
from google.auth.credentials import AnonymousCredentials
from google.auth.transport.requests import AuthorizedSession
try:
    AuthorizedSession(AnonymousCredentials()).request("GET", "https://firestore.googleapis.com/v1/projects/x", timeout=2)
except Exception:
    pass
""",
    "google_auth_request_call": """
import google.auth.transport.requests as g
try:
    g.Request()("https://oauth2.googleapis.com/token", method="POST")
except Exception:
    pass
""",
    "httpx": """
import httpx
try:
    httpx.Client(timeout=2).get("https://generativelanguage.googleapis.com/v1beta/models")
except Exception:
    pass
""",
    "urllib": """
import urllib.request
try:
    urllib.request.urlopen("https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com", timeout=2)
except Exception:
    pass
""",
    "grpc_channel": """
import grpc
try:
    grpc.secure_channel("firestore.googleapis.com:443", grpc.ssl_channel_credentials())
except Exception:
    pass
""",
    "real_firestore_client_get": """
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
try:
    firestore.Client(project="harness-selftest", credentials=AnonymousCredentials()).collection("a").document("b").get(timeout=2)
except Exception:
    pass
""",
    "socket_getaddrinfo": """
import socket
try:
    socket.getaddrinfo("selftest.firebasedatabase.app", 443)
except Exception:
    pass
""",
    "rtdb_host_from_env": """
import os, socket
from urllib.parse import urlparse
h = urlparse(os.environ["FIREBASE_RTDB_URL"]).hostname
try:
    socket.create_connection((h, 443), timeout=2)
except Exception:
    pass
""",
}


def run_tripwire_tests(scratch: str) -> bool:
    ok_all = True
    env = os.environ.copy()
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "grpc_proxy", "ALL_PROXY"):
        env[k] = "http://127.0.0.1:9"
    env.pop("NO_PROXY", None)
    env.pop("no_proxy", None)
    # a syntactically valid but fake RTDB URL, so the env-host rule is tested
    # without touching the real one
    env["FIREBASE_RTDB_URL"] = "https://harness-selftest-default-rtdb.example-rtdb-host.test"
    for name, body in CASES.items():
        rd = os.path.join(scratch, "tripwire_" + name)
        os.makedirs(rd, exist_ok=True)
        hit = os.path.join(rd, "TRIPWIRE_HIT.txt")
        if os.path.exists(hit):
            os.remove(hit)
        code = PRE.format(hd=HARNESS_DIR, rd=rd) + body + "\nprint('TRIPWIRE DID NOT FIRE')\n"
        if name == "rtdb_host_from_env":
            code = code.replace("HF.install_tripwire", "HF._BLOCKED_SUFFIXES.clear(); HF.install_tripwire")
        p = subprocess.run([sys.executable, "-B", "-c", code], env=env, capture_output=True, timeout=60)
        ok = p.returncode == 99 and os.path.exists(hit) and b"DID NOT FIRE" not in p.stdout
        ok_all &= ok
        print(f"[SELFTEST] tripwire {name:32s} exit={p.returncode} hit_file={os.path.exists(hit)} -> "
              f"{'OK' if ok else 'FAIL'}")
        if not ok:
            print(p.stdout.decode("utf-8", "replace").encode("ascii", "backslashreplace").decode()[-800:])
            print(p.stderr.decode("utf-8", "replace").encode("ascii", "backslashreplace").decode()[-1500:])
    return ok_all


FAKES_TEST = r"""
import sys, os, json
sys.dont_write_bytecode = True
sys.path.insert(0, {hd!r})
import harness_fakes as HF
HF.install_tripwire({rd!r})
store = HF.install_fakes({rd!r})
import firebase_admin
from firebase_admin import db, firestore, credentials
from google.cloud.firestore_v1.base_query import FieldFilter
from google.api_core import exceptions as gexc
res = {{}}
def check(name, cond):
    res[name] = bool(cond)

cred = credentials.Certificate("does-not-exist.json")
firebase_admin.initialize_app(cred, {{"databaseURL": "https://x.test"}})
try:
    firebase_admin.initialize_app(cred); check("double_init_raises", False)
except ValueError:
    check("double_init_raises", True)

# RTDB
db.reference("/positions/p1").set({{"x": 8.0, "y": 6.25, "radius_m": None, "anchor_ap_mac": None, "is_approximate": False}})
v = db.reference("/positions/p1").get()
check("rtdb_null_pruned", "radius_m" not in v and "anchor_ap_mac" not in v)
check("rtdb_whole_float_to_int", v["x"] == 8 and type(v["x"]) is int and v["y"] == 6.25)
check("rtdb_bool_kept", v["is_approximate"] is False)
db.reference("/alerts/a1").set({{"resolved": False, "t": "x"}})
db.reference("/alerts/a1").update({{"resolved": True}})
check("rtdb_update", db.reference("/alerts/a1").get() == {{"resolved": True, "t": "x"}})
db.reference("/").child("alerts").update({{"a2/resolved": True, "a1": None}})
check("rtdb_multipath_update", db.reference("/alerts").get() == {{"a2": {{"resolved": True}}}})
db.reference("/alerts/a2").delete()
check("rtdb_delete_prunes_parent", db.reference("/alerts").get() is None and "alerts" not in store.rtdb)
check("rtdb_missing_none", db.reference("/nope/x").get() is None)
try:
    db.reference("/bad.path"); check("rtdb_bad_path_raises", False)
except ValueError:
    check("rtdb_bad_path_raises", True)
try:
    db.reference("/x").set(None); check("rtdb_set_none_raises", False)
except ValueError:
    check("rtdb_set_none_raises", True)
try:
    db.reference("/x").set({{"a": float("nan")}}); check("rtdb_nan_raises", False)
except Exception as e:
    check("rtdb_nan_raises", type(e).__name__ == "InvalidArgumentError")
r = db.reference("/logs").push({{"a": 1}})
check("rtdb_push", db.reference("/logs/" + r.key).get() == {{"a": 1}})
try:
    db.reference("/positions").order_by_child("x"); check("rtdb_unimpl_loud", False)
except NotImplementedError:
    check("rtdb_unimpl_loud", True)

# Firestore
fs = firestore.client()
b = fs.collection("buildings").document("b1")
b.set({{"id": "b1", "created_at": "2026-01-01"}})
fl = b.collection("floors")
fl.document("f2").set({{"id": "f2", "floor_number": 2, "is_active": False}})
fl.document("f1").set({{"id": "f1", "floor_number": 1, "is_active": True}})
fs.collection("buildings").document("b2").collection("floors").document("f9").set({{"id": "f9", "floor_number": 1, "is_active": True}})
check("fs_get", b.get().exists and b.get().to_dict()["id"] == "b1" and b.get().id == "b1")
check("fs_missing", not fs.collection("x").document("y").get().exists and fs.collection("x").document("y").get().to_dict() is None)
check("fs_order_by", [d.id for d in fl.order_by("floor_number").stream()] == ["f1", "f2"])
check("fs_order_desc", [d.id for d in fl.order_by("floor_number", direction=firestore.Query.DESCENDING).stream()] == ["f2", "f1"])
check("fs_where_filter_limit", [d.id for d in fl.where(filter=FieldFilter("is_active", "==", True)).limit(1).stream()] == ["f1"])
check("fs_group", sorted(d.id for d in fs.collection_group("floors").where(filter=FieldFilter("is_active", "==", True)).stream()) == ["f1", "f9"])
check("fs_where_positional", [d.id for d in fl.where("floor_number", "==", 2).stream()] == ["f2"])
check("fs_bool_not_int", [d.id for d in fl.where("floor_number", "==", True).stream()] == [])
check("fs_chain_where", [d.id for d in fl.where("floor_number", "==", 1).where("is_active", "==", True).stream()] == ["f1"])
fl.document("f1").update({{"is_active": False, "meta.x": 1}})
check("fs_update_dotted", fl.document("f1").get().to_dict()["meta"] == {{"x": 1}})
try:
    fl.document("zzz").update({{"a": 1}}); check("fs_update_missing_notfound", False)
except gexc.NotFound:
    check("fs_update_missing_notfound", True)
bt = fs.batch()
for d in fl.stream():
    bt.update(d.reference, {{"is_active": False}})
bt.update(fl.document("f2"), {{"is_active": True}})
bt.commit()
check("fs_batch", [d.id for d in fl.where("is_active", "==", True).stream()] == ["f2"])
fl.document("f2").delete()
check("fs_delete", not fl.document("f2").get().exists)
check("fs_users_empty_limit", list(fs.collection("users").limit(1).stream()) == [])
try:
    fs.collection("a").document("b").set({{"t": firestore.SERVER_TIMESTAMP}}); check("fs_sentinel_loud", False)
except NotImplementedError:
    check("fs_sentinel_loud", True)
try:
    fs.transaction(); check("fs_txn_loud", False)
except NotImplementedError:
    check("fs_txn_loud", True)
try:
    fl.start_after({{}}); check("fs_query_unimpl_loud", False)
except NotImplementedError:
    check("fs_query_unimpl_loud", True)
snap = fl.document("f1").get()
d = snap.to_dict(); d["id"] = "mutated"
check("fs_returns_copies", fl.document("f1").get().to_dict()["id"] == "f1")
check("unimpl_file_written", os.path.exists(os.path.join({rd!r}, "UNIMPLEMENTED.txt")))
HF.dump_state({rd!r})
check("state_dump", json.load(open(os.path.join({rd!r}, "state.json"), encoding="utf-8"))["firestore"]["buildings/b1"]["id"] == "b1")
print("RESULTS " + json.dumps(res))
"""


def run_fake_tests(scratch: str) -> bool:
    import json
    rd = os.path.join(scratch, "fakes_unit")
    os.makedirs(rd, exist_ok=True)
    for f in os.listdir(rd):
        os.remove(os.path.join(rd, f))
    env = os.environ.copy()
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "grpc_proxy"):
        env[k] = "http://127.0.0.1:9"
    p = subprocess.run([sys.executable, "-B", "-c", FAKES_TEST.format(hd=HARNESS_DIR, rd=rd)],
                       env=env, capture_output=True, timeout=120)
    out = p.stdout.decode("utf-8", "replace")
    line = next((ln for ln in out.splitlines() if ln.startswith("RESULTS ")), None)
    if not line:
        print(f"[SELFTEST] fakes: no results, exit={p.returncode}")
        print(p.stderr.decode("utf-8", "replace").encode("ascii", "backslashreplace").decode()[-3000:])
        return False
    res = json.loads(line[len("RESULTS "):])
    bad = [k for k, v in res.items() if not v]
    print(f"[SELFTEST] fakes: {len(res) - len(bad)}/{len(res)} OK" + (f" FAILED: {bad}" if bad else ""))
    return not bad and p.returncode == 0


if __name__ == "__main__":
    scratch = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HARNESS_DIR, "runs", "selftest"))
    os.makedirs(scratch, exist_ok=True)
    a = run_tripwire_tests(scratch)
    b = run_fake_tests(scratch)
    print(f"[SELFTEST] tripwire={'PASS' if a else 'FAIL'} fakes={'PASS' if b else 'FAIL'}")
    sys.exit(0 if (a and b) else 1)
