"""In-memory fakes for firebase_admin RTDB + Firestore, plus a network tripwire.

install_tripwire(run_dir) and install_fakes(run_dir) MUST both run before the
backend's main.py (or any repository module) is imported.

Loudness contract:
  * Any Firestore/RTDB operation the fakes do not implement raises
    NotImplementedError("<op>") AND is recorded to <run_dir>/UNIMPLEMENTED.txt
    and stderr first - app code that swallows `except Exception` (e.g. the
    heartbeat writer) cannot hide it.
  * Any outbound Google/Firebase network attempt (requests, google-auth,
    httpx, urllib, gRPC channel creation, raw DNS/socket) writes
    <run_dir>/TRIPWIRE_HIT.txt + a stderr banner and hard-exits the process
    with code 99 (os._exit, so no `except Exception` anywhere can swallow it).
"""
from __future__ import annotations

import copy
import datetime as _dt
import functools
import json
import math
import os
import random
import string
import sys
import threading
import time
import traceback
import types
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

TRIPWIRE_EXIT_CODE = 99

_RUN_DIR: Optional[str] = None
_LOG_LOCK = threading.Lock()


def _thread_name() -> str:
    return threading.current_thread().name


def _append_line(fname: str, text: str) -> None:
    if not _RUN_DIR:
        return
    with _LOG_LOCK:
        with open(os.path.join(_RUN_DIR, fname), "a", encoding="utf-8") as f:
            f.write(text)


def _stderr(msg: str) -> None:
    # sys.__stderr__: the real process stderr, independent of any tee the app
    # installs on sys.stderr. ASCII-escaped so it can never raise on encode.
    try:
        s = msg.encode("ascii", "backslashreplace").decode("ascii")
        (sys.__stderr__ or sys.stderr).write(s + "\n")
        (sys.__stderr__ or sys.stderr).flush()
    except Exception:
        pass


def unimplemented(op: str):
    """Record + raise for an operation the fakes do not support."""
    stack = "".join(traceback.format_stack(limit=12)[:-1])
    _append_line("UNIMPLEMENTED.txt", f"=== {time.time():.3f} [{_thread_name()}] {op}\n{stack}\n")
    _stderr(f"[HARNESS][FAKE-UNIMPLEMENTED] {op} (thread {_thread_name()})")
    raise NotImplementedError(f"harness fake does not implement: {op}")


# ════════════════════════════════════════════════════════════════════════════
# Tripwire
# ════════════════════════════════════════════════════════════════════════════
_BLOCKED_SUFFIXES = [
    "googleapis.com", "firebaseio.com", "firebasedatabase.app", "google.com",
    "firebasestorage.app", "appspot.com", "gstatic.com", "googleusercontent.com",
    "firebaseapp.com", "cloudfunctions.net", "run.app", "web.app",
    "googleapis.cn", "google.cn", "firebase.com",
]
_TRIPPED = threading.Event()


def _extra_blocked_hosts_from_env() -> None:
    for var in ("FIREBASE_RTDB_URL",):
        v = os.environ.get(var) or ""
        try:
            h = urlparse(v).hostname
        except Exception:
            h = None
        if h and h.lower() not in _BLOCKED_SUFFIXES:
            _BLOCKED_SUFFIXES.append(h.lower())


def _host_blocked(host: Any) -> bool:
    if host is None:
        return False
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    h = str(host).strip().lower().rstrip(".").strip("[]")
    if not h:
        return False
    return any(h == s or h.endswith("." + s) for s in _BLOCKED_SUFFIXES)


def _url_host(url: Any) -> Optional[str]:
    try:
        return urlparse(str(url)).hostname
    except Exception:
        return None


def trip(kind: str, target: str) -> None:
    """Hard, unswallowable failure. Never returns."""
    _TRIPPED.set()
    stack = "".join(traceback.format_stack(limit=25)[:-1])
    try:
        _append_line("TRIPWIRE_HIT.txt",
                     f"=== {time.time():.3f} [{_thread_name()}] kind={kind} target={target}\n{stack}\n")
    except Exception:
        pass
    _stderr("#" * 78)
    _stderr(f"[HARNESS][TRIPWIRE] BLOCKED OUTBOUND {kind} -> {target} (thread {_thread_name()})")
    _stderr(stack)
    _stderr("[HARNESS][TRIPWIRE] hard-exiting with code %d" % TRIPWIRE_EXIT_CODE)
    _stderr("#" * 78)
    for s in (sys.stdout, sys.stderr, sys.__stdout__, sys.__stderr__):
        try:
            s.flush()
        except Exception:
            pass
    os._exit(TRIPWIRE_EXIT_CODE)


def install_tripwire(run_dir: Optional[str]) -> List[str]:
    """Patch every outbound path we know of. Returns the list of patch points."""
    global _RUN_DIR
    if run_dir:
        _RUN_DIR = run_dir
    _extra_blocked_hosts_from_env()
    installed: List[str] = []

    # -- raw socket layer (catch-all for any pure-python HTTP stack) --------
    import socket
    _orig_getaddrinfo = socket.getaddrinfo
    _orig_create_connection = socket.create_connection
    _orig_gethostbyname = socket.gethostbyname
    _orig_gethostbyname_ex = socket.gethostbyname_ex

    def getaddrinfo(host, *a, **kw):
        if _host_blocked(host):
            trip("socket.getaddrinfo", str(host))
        return _orig_getaddrinfo(host, *a, **kw)

    def create_connection(address, *a, **kw):
        try:
            host = address[0]
        except Exception:
            host = None
        if _host_blocked(host):
            trip("socket.create_connection", str(address))
        return _orig_create_connection(address, *a, **kw)

    def gethostbyname(host):
        if _host_blocked(host):
            trip("socket.gethostbyname", str(host))
        return _orig_gethostbyname(host)

    def gethostbyname_ex(host):
        if _host_blocked(host):
            trip("socket.gethostbyname_ex", str(host))
        return _orig_gethostbyname_ex(host)

    socket.getaddrinfo = getaddrinfo
    socket.create_connection = create_connection
    socket.gethostbyname = gethostbyname
    socket.gethostbyname_ex = gethostbyname_ex
    installed += ["socket.getaddrinfo", "socket.create_connection",
                  "socket.gethostbyname", "socket.gethostbyname_ex"]

    # -- requests (firebase_admin RTDB + google-auth token refresh use it) --
    try:
        import requests
        import requests.adapters
        _orig_req = requests.Session.request
        _orig_send = requests.Session.send
        _orig_adapter_send = requests.adapters.HTTPAdapter.send

        def s_request(self, method, url, *a, **kw):
            if _host_blocked(_url_host(url)):
                trip("requests.Session.request", f"{method} {url}")
            return _orig_req(self, method, url, *a, **kw)

        def s_send(self, request, **kw):
            if _host_blocked(_url_host(getattr(request, "url", ""))):
                trip("requests.Session.send", f"{getattr(request, 'method', '?')} {request.url}")
            return _orig_send(self, request, **kw)

        def a_send(self, request, *a, **kw):
            if _host_blocked(_url_host(getattr(request, "url", ""))):
                trip("requests.HTTPAdapter.send", f"{getattr(request, 'method', '?')} {request.url}")
            return _orig_adapter_send(self, request, *a, **kw)

        requests.Session.request = s_request
        requests.Session.send = s_send
        requests.adapters.HTTPAdapter.send = a_send
        installed += ["requests.Session.request", "requests.Session.send", "requests.HTTPAdapter.send"]
    except ImportError:
        pass

    # -- google-auth transports ------------------------------------------------
    try:
        import google.auth.transport.requests as gatr
        _orig_as_req = gatr.AuthorizedSession.request
        _orig_gr_call = gatr.Request.__call__

        def as_request(self, method, url, *a, **kw):
            if _host_blocked(_url_host(url)):
                trip("google.auth AuthorizedSession.request", f"{method} {url}")
            return _orig_as_req(self, method, url, *a, **kw)

        def gr_call(self, url, method="GET", *a, **kw):
            if _host_blocked(_url_host(url)):
                trip("google.auth Request.__call__", f"{method} {url}")
            return _orig_gr_call(self, url, method, *a, **kw)

        gatr.AuthorizedSession.request = as_request
        gatr.Request.__call__ = gr_call
        installed += ["google.auth.transport.requests.AuthorizedSession.request",
                      "google.auth.transport.requests.Request.__call__"]
    except ImportError:
        pass

    # -- httpx (google-genai) ------------------------------------------------------
    try:
        import httpx
        _orig_hx_send = httpx.Client.send
        _orig_hx_asend = httpx.AsyncClient.send

        def hx_send(self, request, *a, **kw):
            if _host_blocked(request.url.host):
                trip("httpx.Client.send", f"{request.method} {request.url}")
            return _orig_hx_send(self, request, *a, **kw)

        async def hx_asend(self, request, *a, **kw):
            if _host_blocked(request.url.host):
                trip("httpx.AsyncClient.send", f"{request.method} {request.url}")
            return await _orig_hx_asend(self, request, *a, **kw)

        httpx.Client.send = hx_send
        httpx.AsyncClient.send = hx_asend
        installed += ["httpx.Client.send", "httpx.AsyncClient.send"]
    except ImportError:
        pass

    # -- urllib ------------------------------------------------------------------
    import urllib.request
    _orig_open = urllib.request.OpenerDirector.open

    def od_open(self, fullurl, *a, **kw):
        url = fullurl if isinstance(fullurl, str) else getattr(fullurl, "full_url", "")
        if _host_blocked(_url_host(url)):
            trip("urllib.OpenerDirector.open", str(url))
        return _orig_open(self, fullurl, *a, **kw)

    urllib.request.OpenerDirector.open = od_open
    installed.append("urllib.request.OpenerDirector.open")

    # -- gRPC (real Firestore client transport). gRPC's C-core resolver does
    #    NOT go through Python's socket module, so channel creation itself is
    #    the choke point. Nothing in this app has a legitimate gRPC channel.
    try:
        import grpc

        def _grpc_trip(name):
            def f(target, *a, **kw):
                trip(name, str(target))
            return f

        for nm in ("secure_channel", "insecure_channel"):
            setattr(grpc, nm, _grpc_trip("grpc." + nm))
            installed.append("grpc." + nm)
        try:
            import grpc.aio as grpc_aio
            for nm in ("secure_channel", "insecure_channel"):
                setattr(grpc_aio, nm, _grpc_trip("grpc.aio." + nm))
                installed.append("grpc.aio." + nm)
        except ImportError:
            pass
        try:
            import google.api_core.grpc_helpers as gh
            gh.create_channel = _grpc_trip("google.api_core.grpc_helpers.create_channel")
            installed.append("google.api_core.grpc_helpers.create_channel")
            import google.api_core.grpc_helpers_async as gha
            gha.create_channel = _grpc_trip("google.api_core.grpc_helpers_async.create_channel")
            installed.append("google.api_core.grpc_helpers_async.create_channel")
        except ImportError:
            pass
    except ImportError:
        pass

    return installed


# ════════════════════════════════════════════════════════════════════════════
# Shared store + op log
# ════════════════════════════════════════════════════════════════════════════
class _Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.rtdb: Dict[str, Any] = {}
        # Firestore: doc path tuple (col, doc, col, doc, ...) -> data dict
        self.fs: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        self.fs_meta: Dict[Tuple[str, ...], Dict[str, float]] = {}
        self.counters: Dict[str, int] = {}
        self.op_logging = True

    def count(self, key: str) -> None:
        self.counters[key] = self.counters.get(key, 0) + 1

    def log(self, fname: str, rec: Dict[str, Any]) -> None:
        if not self.op_logging:
            return
        rec = {"t": round(time.time(), 4), "thread": _thread_name(), **rec}
        try:
            line = json.dumps(rec, ensure_ascii=False, default=str)
        except Exception as e:  # pragma: no cover
            line = json.dumps({"t": rec["t"], "log_error": repr(e)})
        _append_line(fname, line + "\n")

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "rtdb": copy.deepcopy(self.rtdb),
                "firestore": {"/".join(p): copy.deepcopy(d) for p, d in sorted(self.fs.items())},
                "counters": dict(self.counters),
            }


STORE = _Store()


# ════════════════════════════════════════════════════════════════════════════
# Fake Realtime Database (firebase_admin.db)
# ════════════════════════════════════════════════════════════════════════════
_RTDB_INVALID_PATH_CHARS = "[].?#$"          # firebase_admin.db._INVALID_PATH_CHARACTERS
_RTDB_INVALID_KEY_CHARS = ".$#[]/"            # server-side key rule


def _rtdb_invalid_arg(msg: str):
    from firebase_admin import exceptions as fa_exc
    return fa_exc.InvalidArgumentError(msg)


def _rtdb_parse_path(path: Any) -> List[str]:
    if not isinstance(path, str):
        raise ValueError('Invalid path: "{0}". Path must be a string.'.format(path))
    if any(ch in path for ch in _RTDB_INVALID_PATH_CHARS):
        raise ValueError('Invalid path: "{0}". Path contains illegal characters.'.format(path))
    return [seg for seg in path.split("/") if seg]


def _rtdb_normalize(value: Any) -> Any:
    """What the RTDB server would store/return for `value`: JSON round trip
    (TypeError for non-serializable, like requests' json=), NaN/Inf rejected,
    nulls and empty containers dropped, whole-number doubles read back as ints."""
    try:
        text = json.dumps(value, allow_nan=False)
    except ValueError as e:
        raise _rtdb_invalid_arg(f"Invalid data (NaN/Infinity not allowed): {e}")
    v = json.loads(text)

    def prune(x):
        if isinstance(x, dict):
            out = {}
            for k, val in x.items():
                if not k or any(ch in k for ch in _RTDB_INVALID_KEY_CHARS):
                    raise _rtdb_invalid_arg(f'Invalid data; key "{k}" contains illegal characters')
                pv = prune(val)
                if pv is not None:
                    out[k] = pv
            return out or None
        if isinstance(x, list):
            items = [prune(i) for i in x]
            return items if any(i is not None for i in items) else None
        if isinstance(x, float) and x.is_integer() and abs(x) < 2 ** 53:
            return int(x)
        return x

    return prune(v)


class FakeRTDB:
    def _get_node(self, segs: List[str]) -> Any:
        node: Any = STORE.rtdb
        for s in segs:
            if not isinstance(node, dict) or s not in node:
                return None
            node = node[s]
        return node

    def _set_node(self, segs: List[str], value: Any) -> None:
        if not segs:
            STORE.rtdb.clear()
            if isinstance(value, dict):
                STORE.rtdb.update(value)
            elif value is not None:
                unimplemented("rtdb set() of a non-object value at root")
            return
        if value is None:
            self._delete_node(segs)
            return
        node = STORE.rtdb
        for s in segs[:-1]:
            nxt = node.get(s)
            if not isinstance(nxt, dict):
                nxt = {}
                node[s] = nxt
            node = nxt
        node[segs[-1]] = value

    def _delete_node(self, segs: List[str]) -> None:
        if not segs:
            STORE.rtdb.clear()
            return
        chain = [STORE.rtdb]
        node: Any = STORE.rtdb
        for s in segs[:-1]:
            if not isinstance(node, dict) or s not in node:
                return
            node = node[s]
            chain.append(node)
        if isinstance(node, dict):
            node.pop(segs[-1], None)
        # RTDB has no empty nodes: prune now-empty ancestors
        for i in range(len(chain) - 1, 0, -1):
            if isinstance(chain[i], dict) and not chain[i]:
                chain[i - 1].pop(segs[i - 1], None)
            else:
                break


_RTDB = FakeRTDB()
_PUSH_CHARS = "-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz"


def _push_id() -> str:
    now = int(time.time() * 1000)
    ts = []
    for _ in range(8):
        ts.append(_PUSH_CHARS[now % 64])
        now //= 64
    return "".join(reversed(ts)) + "".join(random.choice(_PUSH_CHARS) for _ in range(12))


class FakeReference:
    def __init__(self, path: str = "/") -> None:
        self._segs = _rtdb_parse_path(path)

    # -- properties -------------------------------------------------------------
    @property
    def key(self) -> Optional[str]:
        return self._segs[-1] if self._segs else None

    @property
    def path(self) -> str:
        return "/" + "/".join(self._segs)

    @property
    def parent(self) -> Optional["FakeReference"]:
        if not self._segs:
            return None
        return FakeReference("/" + "/".join(self._segs[:-1]))

    def child(self, path: str) -> "FakeReference":
        if not path or not isinstance(path, str):
            raise ValueError('Invalid path argument: "{0}". Path must be a non-empty string.'.format(path))
        if path.startswith("/"):
            raise ValueError('Invalid path argument: "{0}". Child path must not start with "/"'.format(path))
        return FakeReference(self.path.rstrip("/") + "/" + path)

    # -- ops ----------------------------------------------------------------------
    def get(self, etag: bool = False, shallow: bool = False):
        if etag:
            unimplemented("rtdb Reference.get(etag=True)")
        if shallow:
            unimplemented("rtdb Reference.get(shallow=True)")
        with STORE.lock:
            STORE.count("rtdb.get")
            val = copy.deepcopy(_RTDB._get_node(self._segs))
            STORE.log("rtdb_ops.jsonl", {"op": "get", "path": self.path, "found": val is not None})
            return val

    def set(self, value: Any) -> None:
        if value is None:
            raise ValueError("Value must not be None.")
        norm = _rtdb_normalize(value)
        with STORE.lock:
            STORE.count("rtdb.set")
            _RTDB._set_node(self._segs, norm)
            STORE.log("rtdb_ops.jsonl", {"op": "set", "path": self.path, "value": norm})

    def update(self, value: Any) -> None:
        if not value or not isinstance(value, dict):
            raise ValueError("Value argument must be a non-empty dictionary.")
        if None in value.keys():
            raise ValueError("Dictionary must not contain None keys.")
        prepared = []
        for k, v in value.items():
            if not isinstance(k, str):
                raise _rtdb_invalid_arg(f"Invalid key {k!r}")
            segs = _rtdb_parse_path(k)
            if not segs:
                raise _rtdb_invalid_arg(f'Invalid update key "{k}"')
            for s in segs:
                if any(ch in s for ch in _RTDB_INVALID_KEY_CHARS):
                    raise _rtdb_invalid_arg(f'Invalid key segment "{s}"')
            prepared.append((segs, None if v is None else _rtdb_normalize(v)))
        with STORE.lock:
            STORE.count("rtdb.update")
            for segs, norm in prepared:
                _RTDB._set_node(self._segs + segs, norm)
            STORE.log("rtdb_ops.jsonl", {"op": "update", "path": self.path,
                                         "value": {"/".join(s): n for s, n in prepared}})

    def delete(self) -> None:
        with STORE.lock:
            STORE.count("rtdb.delete")
            _RTDB._delete_node(self._segs)
            STORE.log("rtdb_ops.jsonl", {"op": "delete", "path": self.path})

    def push(self, value: Any = "") -> "FakeReference":
        if value is None:
            raise ValueError("Value must not be None.")
        ref = self.child(_push_id())
        ref.set(value)
        return ref

    # -- not implemented (loud) -------------------------------------------------
    def order_by_child(self, *a, **kw):
        unimplemented("rtdb Reference.order_by_child")

    def order_by_key(self, *a, **kw):
        unimplemented("rtdb Reference.order_by_key")

    def order_by_value(self, *a, **kw):
        unimplemented("rtdb Reference.order_by_value")

    def transaction(self, *a, **kw):
        unimplemented("rtdb Reference.transaction")

    def listen(self, *a, **kw):
        unimplemented("rtdb Reference.listen")

    def get_if_changed(self, *a, **kw):
        unimplemented("rtdb Reference.get_if_changed")

    def set_if_unchanged(self, *a, **kw):
        unimplemented("rtdb Reference.set_if_unchanged")

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"rtdb Reference.{name}")


def _make_fake_db_module() -> types.ModuleType:
    m = types.ModuleType("firebase_admin.db")
    m.__file__ = __file__ + "#fake_db"

    def reference(path: str = "/", app=None, url=None) -> FakeReference:
        if url is not None:
            unimplemented("rtdb db.reference(url=...)")
        return FakeReference(path)

    m.reference = reference
    m.Reference = FakeReference
    m._INVALID_PATH_CHARACTERS = _RTDB_INVALID_PATH_CHARS

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"firebase_admin.db.{name}")

    m.__getattr__ = __getattr__
    return m


# ════════════════════════════════════════════════════════════════════════════
# Fake Firestore (firebase_admin.firestore)
# ════════════════════════════════════════════════════════════════════════════
def _fs_transform_types():
    try:
        from google.cloud.firestore_v1 import transforms as t
        return (t.Sentinel, t._ValueList, t._NumericValue)
    except Exception:  # pragma: no cover
        return tuple()


_FS_TRANSFORM_TYPES: tuple = ()


def _fs_check_value(v: Any, where: str) -> Any:
    """Deep-copy + validate a value the way Firestore would accept it."""
    if _FS_TRANSFORM_TYPES and isinstance(v, _FS_TRANSFORM_TYPES):
        unimplemented(f"firestore sentinel/transform value {v!r} in {where}")
    if v is None or isinstance(v, (bool, int, float, str, bytes)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return v  # Firestore accepts NaN/Inf doubles
        return v
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v
    if isinstance(v, (list, tuple)):
        return [_fs_check_value(i, where) for i in v]
    if isinstance(v, dict):
        out = {}
        for k, val in v.items():
            if not isinstance(k, str):
                raise TypeError(f"Firestore map keys must be str, got {type(k).__name__}")
            out[k] = _fs_check_value(val, where)
        return out
    # e.g. numpy.float64 is a float subclass -> handled above; anything else is
    # what the real client would also refuse to encode.
    raise TypeError(f"Cannot convert to a Firestore Value: {v!r} ({type(v).__name__}) in {where}")


def _fs_get_field(data: Dict[str, Any], field_path: str) -> Tuple[bool, Any]:
    node: Any = data
    for part in field_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    return True, node


def _fs_set_field(data: Dict[str, Any], field_path: str, value: Any) -> None:
    parts = field_path.split(".")
    node = data
    for p in parts[:-1]:
        nxt = node.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            node[p] = nxt
        node = nxt
    node[parts[-1]] = value


def _fs_deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> None:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _fs_deep_merge(dst[k], v)
        else:
            dst[k] = v


def _fs_type_rank(v: Any) -> int:
    # Firestore cross-type ordering: null < bool < number < timestamp < string < bytes < ref < geo < array < map
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1
    if isinstance(v, (int, float)):
        return 2
    if isinstance(v, (_dt.datetime, _dt.date)):
        return 3
    if isinstance(v, str):
        return 4
    if isinstance(v, bytes):
        return 5
    if isinstance(v, list):
        return 8
    if isinstance(v, dict):
        return 9
    return 10


def _fs_eq(a: Any, b: Any) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if _fs_type_rank(a) != _fs_type_rank(b):
        return False
    return a == b


def _fs_cmp(a: Any, b: Any) -> int:
    ra, rb = _fs_type_rank(a), _fs_type_rank(b)
    if ra != rb:
        return -1 if ra < rb else 1
    if a == b:
        return 0
    try:
        return -1 if a < b else 1
    except TypeError:
        sa, sb = json.dumps(a, default=str, sort_keys=True), json.dumps(b, default=str, sort_keys=True)
        return -1 if sa < sb else (1 if sa > sb else 0)


def _fs_match(data: Dict[str, Any], field: str, op: str, value: Any) -> bool:
    present, v = _fs_get_field(data, field)
    if op == "==":
        return present and _fs_eq(v, value)
    if op == "!=":
        return present and v is not None and not _fs_eq(v, value)
    if op in ("<", "<=", ">", ">="):
        if not present or _fs_type_rank(v) != _fs_type_rank(value):
            return False
        c = _fs_cmp(v, value)
        return {"<": c < 0, "<=": c <= 0, ">": c > 0, ">=": c >= 0}[op]
    if op == "in":
        return present and any(_fs_eq(v, x) for x in value)
    if op == "not-in":
        return present and v is not None and not any(_fs_eq(v, x) for x in value)
    if op == "array_contains":
        return present and isinstance(v, list) and any(_fs_eq(i, value) for i in v)
    if op == "array_contains_any":
        return present and isinstance(v, list) and any(_fs_eq(i, x) for i in v for x in value)
    unimplemented(f"firestore where op_string={op!r}")
    return False


def _fs_not_found(path: str):
    from google.api_core import exceptions as gexc
    return gexc.NotFound(f"No document to update: {path}")


def _fs_conflict(path: str):
    from google.api_core import exceptions as gexc
    return gexc.Conflict(f"Document already exists: {path}")


def _auto_id() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(20))


class FakeDocumentSnapshot:
    def __init__(self, ref: "FakeDocumentReference", data: Optional[Dict[str, Any]],
                 meta: Optional[Dict[str, float]]) -> None:
        self.reference = ref
        self._data = data
        now = _dt.datetime.now(_dt.timezone.utc)
        self.read_time = now
        self.create_time = (_dt.datetime.fromtimestamp(meta["create"], _dt.timezone.utc) if meta else None)
        self.update_time = (_dt.datetime.fromtimestamp(meta["update"], _dt.timezone.utc) if meta else None)

    @property
    def exists(self) -> bool:
        return self._data is not None

    @property
    def id(self) -> str:
        return self.reference.id

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return copy.deepcopy(self._data) if self._data is not None else None

    def get(self, field_path: str) -> Any:
        if self._data is None:
            return None
        present, v = _fs_get_field(self._data, field_path)
        if not present:
            raise KeyError(f"'{field_path}' is not contained in the data")
        return copy.deepcopy(v)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"firestore DocumentSnapshot.{name}")


class FakeDocumentReference:
    def __init__(self, client: "FakeFirestoreClient", path: Tuple[str, ...]) -> None:
        if len(path) % 2 != 0 or not path:
            raise ValueError(f"A document must have an even number of path elements: {path}")
        for seg in path:
            if not isinstance(seg, str) or not seg or "/" in seg:
                raise ValueError(f"Invalid path segment {seg!r}")
        self._client = client
        self._path = tuple(path)

    @property
    def id(self) -> str:
        return self._path[-1]

    @property
    def path(self) -> str:
        return "/".join(self._path)

    @property
    def parent(self) -> "FakeCollectionReference":
        return FakeCollectionReference(self._client, self._path[:-1])

    def collection(self, collection_id: str) -> "FakeCollectionReference":
        return FakeCollectionReference(self._client, self._path + tuple(collection_id.split("/")))

    def get(self, field_paths=None, transaction=None, **kw) -> FakeDocumentSnapshot:
        if field_paths is not None:
            unimplemented("firestore DocumentReference.get(field_paths=...)")
        if transaction is not None:
            unimplemented("firestore DocumentReference.get(transaction=...)")
        with STORE.lock:
            STORE.count("fs.doc.get")
            data = STORE.fs.get(self._path)
            snap = FakeDocumentSnapshot(self, copy.deepcopy(data) if data is not None else None,
                                        dict(STORE.fs_meta.get(self._path, {})) or None)
            STORE.log("firestore_ops.jsonl", {"op": "doc.get", "path": self.path, "found": data is not None})
            return snap

    # write primitives (also used by the batch) ---------------------------------
    def _apply_set(self, data: Dict[str, Any], merge: bool) -> None:
        now = time.time()
        if merge and self._path in STORE.fs:
            _fs_deep_merge(STORE.fs[self._path], data)
        else:
            STORE.fs[self._path] = data
        meta = STORE.fs_meta.setdefault(self._path, {"create": now})
        meta["update"] = now

    def _prepare_set(self, document_data: Dict[str, Any], merge: Any) -> Tuple[Dict[str, Any], bool]:
        if merge not in (False, True):
            unimplemented("firestore set(merge=<field list>)")
        if not isinstance(document_data, dict):
            raise TypeError("document_data must be a dict")
        return _fs_check_value(document_data, f"set({self.path})"), bool(merge)

    def _prepare_update(self, field_updates: Dict[str, Any]) -> List[Tuple[str, Any]]:
        if not isinstance(field_updates, dict) or not field_updates:
            raise ValueError("Cannot update with an empty document.")
        out = []
        for k, v in field_updates.items():
            if not isinstance(k, str):
                unimplemented("firestore update() with non-str (FieldPath) key")
            out.append((k, _fs_check_value(v, f"update({self.path})")))
        return out

    def _apply_update(self, prepared: List[Tuple[str, Any]]) -> None:
        if self._path not in STORE.fs:
            raise _fs_not_found(self.path)
        doc = STORE.fs[self._path]
        for k, v in prepared:
            _fs_set_field(doc, k, v)
        STORE.fs_meta.setdefault(self._path, {"create": time.time()})["update"] = time.time()

    def _apply_delete(self) -> None:
        STORE.fs.pop(self._path, None)
        STORE.fs_meta.pop(self._path, None)

    def set(self, document_data: Dict[str, Any], merge: Any = False) -> Dict[str, Any]:
        data, m = self._prepare_set(document_data, merge)
        with STORE.lock:
            STORE.count("fs.doc.set")
            self._apply_set(data, m)
            STORE.log("firestore_ops.jsonl", {"op": "doc.set", "path": self.path, "merge": m, "value": data})
        return {"update_time": _dt.datetime.now(_dt.timezone.utc)}

    def create(self, document_data: Dict[str, Any]) -> Dict[str, Any]:
        data, _ = self._prepare_set(document_data, False)
        with STORE.lock:
            if self._path in STORE.fs:
                raise _fs_conflict(self.path)
            STORE.count("fs.doc.create")
            self._apply_set(data, False)
            STORE.log("firestore_ops.jsonl", {"op": "doc.create", "path": self.path, "value": data})
        return {"update_time": _dt.datetime.now(_dt.timezone.utc)}

    def update(self, field_updates: Dict[str, Any], option=None) -> Dict[str, Any]:
        if option is not None:
            unimplemented("firestore DocumentReference.update(option=...)")
        prepared = self._prepare_update(field_updates)
        with STORE.lock:
            STORE.count("fs.doc.update")
            self._apply_update(prepared)
            STORE.log("firestore_ops.jsonl", {"op": "doc.update", "path": self.path, "value": dict(prepared)})
        return {"update_time": _dt.datetime.now(_dt.timezone.utc)}

    def delete(self, option=None) -> _dt.datetime:
        if option is not None:
            unimplemented("firestore DocumentReference.delete(option=...)")
        with STORE.lock:
            STORE.count("fs.doc.delete")
            self._apply_delete()
            STORE.log("firestore_ops.jsonl", {"op": "doc.delete", "path": self.path})
        return _dt.datetime.now(_dt.timezone.utc)

    def collections(self, *a, **kw):
        unimplemented("firestore DocumentReference.collections")

    def on_snapshot(self, *a, **kw):
        unimplemented("firestore DocumentReference.on_snapshot")

    def __eq__(self, other):
        return isinstance(other, FakeDocumentReference) and other._path == self._path

    def __hash__(self):
        return hash(self._path)

    def __repr__(self):
        return f"<FakeDocumentReference {self.path}>"

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"firestore DocumentReference.{name}")


class FakeQuery:
    def __init__(self, client: "FakeFirestoreClient", parent_path: Optional[Tuple[str, ...]],
                 group_id: Optional[str] = None, filters=None, orders=None, limit_n=None) -> None:
        self._client = client
        self._parent_path = parent_path      # collection path for a normal query
        self._group_id = group_id            # collection id for a collection-group query
        self._filters: List[Tuple[str, str, Any]] = list(filters or [])
        self._orders: List[Tuple[str, str]] = list(orders or [])
        self._limit: Optional[int] = limit_n

    def _copy(self, **kw) -> "FakeQuery":
        q = FakeQuery(self._client, self._parent_path, self._group_id,
                      self._filters, self._orders, self._limit)
        for k, v in kw.items():
            setattr(q, k, v)
        return q

    def _describe(self) -> str:
        base = f"group:{self._group_id}" if self._group_id else "/".join(self._parent_path or ())
        return f"{base} where={self._filters} order={self._orders} limit={self._limit}"

    def where(self, field_path=None, op_string=None, value=None, *, filter=None) -> "FakeQuery":
        if filter is not None:
            if field_path is not None or op_string is not None or value is not None:
                raise ValueError("Can't pass in both the positional arguments and 'filter' at the same time")
            if type(filter).__name__ != "FieldFilter" or not hasattr(filter, "op_string"):
                unimplemented(f"firestore where(filter={type(filter).__name__}) (composite And/Or)")
            f = (filter.field_path, filter.op_string, filter.value)
        else:
            if field_path is None or op_string is None:
                raise ValueError("where() requires field_path and op_string")
            f = (field_path, op_string, value)
        if not isinstance(f[0], str):
            unimplemented("firestore where() with FieldPath object")
        return self._copy(_filters=self._filters + [f])

    def order_by(self, field_path, direction="ASCENDING") -> "FakeQuery":
        if direction not in ("ASCENDING", "DESCENDING"):
            raise ValueError(f"Invalid direction {direction!r}")
        if not isinstance(field_path, str):
            unimplemented("firestore order_by() with FieldPath object")
        return self._copy(_orders=self._orders + [(field_path, direction)])

    def limit(self, count: int) -> "FakeQuery":
        return self._copy(_limit=int(count))

    def _run(self) -> List[FakeDocumentSnapshot]:
        with STORE.lock:
            cands = []
            for path, data in STORE.fs.items():
                if self._group_id is not None:
                    if len(path) < 2 or path[-2] != self._group_id:
                        continue
                else:
                    pp = self._parent_path or ()
                    if len(path) != len(pp) + 1 or path[:-1] != pp:
                        continue
                cands.append((path, data))
            res = []
            for path, data in cands:
                if all(_fs_match(data, fp, op, val) for fp, op, val in self._filters):
                    res.append((path, data))
            # Docs lacking an order_by field are excluded (real Firestore behaviour)
            for fp, _dir in self._orders:
                res = [(p, d) for p, d in res if _fs_get_field(d, fp)[0]]
            # Default order: by document path (__name__); then apply order_bys (stable)
            res.sort(key=lambda pd: pd[0])
            for fp, direction in reversed(self._orders):
                res.sort(key=functools.cmp_to_key(
                    lambda x, y, fp=fp: _fs_cmp(_fs_get_field(x[1], fp)[1], _fs_get_field(y[1], fp)[1])),
                    reverse=(direction == "DESCENDING"))
            if self._limit is not None:
                res = res[: self._limit]
            snaps = [FakeDocumentSnapshot(FakeDocumentReference(self._client, p), copy.deepcopy(d),
                                          dict(STORE.fs_meta.get(p, {})) or None) for p, d in res]
            STORE.count("fs.query")
            STORE.log("firestore_ops.jsonl", {"op": "query", "query": self._describe(), "n": len(snaps)})
            return snaps

    def stream(self, transaction=None, **kw):
        if transaction is not None:
            unimplemented("firestore Query.stream(transaction=...)")
        return iter(self._run())

    def get(self, transaction=None, **kw):
        if transaction is not None:
            unimplemented("firestore Query.get(transaction=...)")
        return self._run()

    # -- not implemented (loud) ---------------------------------------------------
    def offset(self, *a, **kw): unimplemented("firestore Query.offset")
    def start_at(self, *a, **kw): unimplemented("firestore Query.start_at")
    def start_after(self, *a, **kw): unimplemented("firestore Query.start_after")
    def end_at(self, *a, **kw): unimplemented("firestore Query.end_at")
    def end_before(self, *a, **kw): unimplemented("firestore Query.end_before")
    def limit_to_last(self, *a, **kw): unimplemented("firestore Query.limit_to_last")
    def select(self, *a, **kw): unimplemented("firestore Query.select")
    def count(self, *a, **kw): unimplemented("firestore Query.count")
    def sum(self, *a, **kw): unimplemented("firestore Query.sum")
    def avg(self, *a, **kw): unimplemented("firestore Query.avg")
    def on_snapshot(self, *a, **kw): unimplemented("firestore Query.on_snapshot")
    def find_nearest(self, *a, **kw): unimplemented("firestore Query.find_nearest")

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"firestore Query.{name}")


class FakeCollectionReference(FakeQuery):
    def __init__(self, client: "FakeFirestoreClient", path: Tuple[str, ...]) -> None:
        if len(path) % 2 != 1:
            raise ValueError(f"A collection must have an odd number of path elements: {path}")
        for seg in path:
            if not isinstance(seg, str) or not seg or "/" in seg:
                raise ValueError(f"Invalid path segment {seg!r}")
        super().__init__(client, tuple(path))
        self._path = tuple(path)

    @property
    def id(self) -> str:
        return self._path[-1]

    @property
    def parent(self) -> Optional[FakeDocumentReference]:
        return FakeDocumentReference(self._client, self._path[:-1]) if len(self._path) > 1 else None

    def document(self, document_id: Optional[str] = None) -> FakeDocumentReference:
        if document_id is None:
            document_id = _auto_id()
        if not isinstance(document_id, str) or "/" in document_id or not document_id:
            raise ValueError(f"Invalid document id {document_id!r}")
        return FakeDocumentReference(self._client, self._path + (document_id,))

    def add(self, document_data: Dict[str, Any], document_id: Optional[str] = None):
        ref = self.document(document_id)
        ref.create(document_data)
        return _dt.datetime.now(_dt.timezone.utc), ref

    def list_documents(self, page_size=None, **kw):
        with STORE.lock:
            ids = sorted({p[len(self._path)] for p in STORE.fs
                          if len(p) > len(self._path) and p[:len(self._path)] == self._path})
        return [self.document(i) for i in ids]

    def __repr__(self):
        return f"<FakeCollectionReference {'/'.join(self._path)}>"


class FakeWriteBatch:
    def __init__(self, client: "FakeFirestoreClient") -> None:
        self._client = client
        self._ops: List[Tuple[str, FakeDocumentReference, Any]] = []
        self._committed = False

    def set(self, reference, document_data, merge=False):
        self._ops.append(("set", reference, reference._prepare_set(document_data, merge)))
        return self

    def create(self, reference, document_data):
        self._ops.append(("create", reference, reference._prepare_set(document_data, False)))
        return self

    def update(self, reference, field_updates, option=None):
        if option is not None:
            unimplemented("firestore WriteBatch.update(option=...)")
        self._ops.append(("update", reference, reference._prepare_update(field_updates)))
        return self

    def delete(self, reference, option=None):
        if option is not None:
            unimplemented("firestore WriteBatch.delete(option=...)")
        self._ops.append(("delete", reference, None))
        return self

    def commit(self, **kw):
        if self._committed:
            raise ValueError("Batch already committed")
        with STORE.lock:
            # validate first: all-or-nothing like the real commit
            exists = {p: True for p in STORE.fs}
            for kind, ref, _ in self._ops:
                if kind == "update" and not exists.get(ref._path):
                    raise _fs_not_found(ref.path)
                if kind == "create" and exists.get(ref._path):
                    raise _fs_conflict(ref.path)
                if kind in ("set", "create"):
                    exists[ref._path] = True
                if kind == "delete":
                    exists[ref._path] = False
            for kind, ref, arg in self._ops:
                if kind in ("set", "create"):
                    ref._apply_set(arg[0], arg[1])
                elif kind == "update":
                    ref._apply_update(arg)
                else:
                    ref._apply_delete()
            STORE.count("fs.batch.commit")
            STORE.log("firestore_ops.jsonl", {"op": "batch.commit",
                                              "ops": [(k, r.path) for k, r, _ in self._ops]})
        self._committed = True
        return [{"update_time": _dt.datetime.now(_dt.timezone.utc)} for _ in self._ops]

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"firestore WriteBatch.{name}")


class FakeFirestoreClient:
    project = "harness-fake-project"

    def collection(self, *collection_path: str) -> FakeCollectionReference:
        parts: List[str] = []
        for p in collection_path:
            parts += [s for s in p.split("/") if s]
        return FakeCollectionReference(self, tuple(parts))

    def document(self, *document_path: str) -> FakeDocumentReference:
        parts: List[str] = []
        for p in document_path:
            parts += [s for s in p.split("/") if s]
        return FakeDocumentReference(self, tuple(parts))

    def collection_group(self, collection_id: str) -> FakeQuery:
        if "/" in collection_id:
            raise ValueError("collection_group id must not contain '/'")
        return FakeQuery(self, None, group_id=collection_id)

    def batch(self) -> FakeWriteBatch:
        return FakeWriteBatch(self)

    def transaction(self, *a, **kw):
        unimplemented("firestore Client.transaction")

    def collections(self, *a, **kw):
        unimplemented("firestore Client.collections")

    def get_all(self, *a, **kw):
        unimplemented("firestore Client.get_all")

    def bulk_writer(self, *a, **kw):
        unimplemented("firestore Client.bulk_writer")

    def recursive_delete(self, *a, **kw):
        unimplemented("firestore Client.recursive_delete")

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"firestore Client.{name}")


_FS_CLIENT = FakeFirestoreClient()


class _FakeQueryConsts:
    ASCENDING = "ASCENDING"
    DESCENDING = "DESCENDING"


def _make_fake_firestore_module() -> types.ModuleType:
    m = types.ModuleType("firebase_admin.firestore")
    m.__file__ = __file__ + "#fake_firestore"

    def client(app=None, database_id=None) -> FakeFirestoreClient:
        if database_id not in (None, "(default)"):
            unimplemented(f"firestore.client(database_id={database_id!r})")
        return _FS_CLIENT

    m.client = client
    m.Query = _FakeQueryConsts
    m.Client = FakeFirestoreClient
    m.CollectionReference = FakeCollectionReference
    m.DocumentReference = FakeDocumentReference
    m.DocumentSnapshot = FakeDocumentSnapshot
    m.WriteBatch = FakeWriteBatch
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
        m.FieldFilter = FieldFilter
        from google.cloud.firestore_v1 import transforms as t
        # Re-exported so references resolve; USING one in set/update is loud.
        for nm in ("SERVER_TIMESTAMP", "DELETE_FIELD", "ArrayUnion", "ArrayRemove",
                   "Increment", "Maximum", "Minimum"):
            setattr(m, nm, getattr(t, nm))
    except Exception:
        pass

    def __getattr__(name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"firebase_admin.firestore.{name}")

    m.__getattr__ = __getattr__
    return m


# ════════════════════════════════════════════════════════════════════════════
# firebase_admin top-level no-ops + install
# ════════════════════════════════════════════════════════════════════════════
class _FakeCredential:
    def __init__(self, source: Any = None) -> None:
        self.source_path = source if isinstance(source, str) else "<dict>"
        self.project_id = "harness-fake-project"

    def get_credential(self):
        unimplemented("credentials.get_credential")

    def get_access_token(self):
        unimplemented("credentials.get_access_token")


class _FakeApp:
    def __init__(self, name: str, credential: Any, options: Optional[dict]) -> None:
        self.name = name
        self.credential = credential
        self.options = dict(options or {})
        self.project_id = "harness-fake-project"

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        unimplemented(f"firebase_admin.App.{name}")


def install_fakes(run_dir: Optional[str]) -> _Store:
    global _RUN_DIR, _FS_TRANSFORM_TYPES
    if run_dir:
        _RUN_DIR = run_dir
    for bad in ("main", "config.settings", "repositories.ap_repository", "firebase_admin.db",
                "firebase_admin.firestore"):
        if bad in sys.modules and not (getattr(sys.modules[bad], "__file__", None) or "").endswith(("#fake_db", "#fake_firestore")):
            if bad.startswith("firebase_admin."):
                raise RuntimeError(f"install_fakes(): real {bad} already imported - fakes must go first")
            raise RuntimeError(f"install_fakes(): {bad} already imported - fakes must go first")

    _FS_TRANSFORM_TYPES = _fs_transform_types()

    import firebase_admin
    import firebase_admin.credentials as fa_creds

    fake_db = _make_fake_db_module()
    fake_fs = _make_fake_firestore_module()
    sys.modules["firebase_admin.db"] = fake_db
    sys.modules["firebase_admin.firestore"] = fake_fs
    firebase_admin.db = fake_db
    firebase_admin.firestore = fake_fs

    def Certificate(cert):  # noqa: N802 - mirrors the real name
        # Deliberately does NOT read the key file (a worktree may not have it).
        return _FakeCredential(cert)

    fa_creds.Certificate = Certificate

    def initialize_app(credential=None, options=None, name="[DEFAULT]"):
        if name in firebase_admin._apps:
            raise ValueError(
                f'The default Firebase app already exists. This means you called initialize_app() more '
                f'than once without providing an app name as the second argument.' if name == "[DEFAULT]"
                else f'Firebase app named "{name}" already exists.')
        app = _FakeApp(name, credential, options)
        firebase_admin._apps[name] = app
        return app

    firebase_admin.initialize_app = initialize_app

    # firebase_admin.auth / storage: not needed by ingest; loud if reached.
    try:
        import firebase_admin.auth as fa_auth

        def _auth_unsupported(name):
            def f(*a, **kw):
                unimplemented(f"firebase_admin.auth.{name}")
            return f

        for nm in ("verify_id_token", "get_user", "create_user", "delete_user", "update_user",
                   "set_custom_user_claims", "revoke_refresh_tokens", "generate_email_verification_link",
                   "get_user_by_email", "create_custom_token", "verify_session_cookie"):
            if hasattr(fa_auth, nm):
                setattr(fa_auth, nm, _auth_unsupported(nm))
    except ImportError:
        pass
    try:
        import firebase_admin.storage as fa_storage
        fa_storage.bucket = lambda *a, **kw: unimplemented("firebase_admin.storage.bucket")
    except ImportError:
        pass

    return STORE


def dump_state(run_dir: str, extra: Optional[Dict[str, Any]] = None) -> bool:
    snap = STORE.snapshot()
    snap["ts"] = time.time()
    snap["iso"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    snap["pid"] = os.getpid()
    if extra:
        snap.update(extra)
    tmp = os.path.join(run_dir, "state.json.tmp")
    dst = os.path.join(run_dir, "state.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1, default=str)
    for _ in range(10):
        try:
            os.replace(tmp, dst)
            return True
        except PermissionError:  # Windows: a reader has the file open
            time.sleep(0.05)
    return False
