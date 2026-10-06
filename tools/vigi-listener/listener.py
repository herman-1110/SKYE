"""VIGI Alarm Server capture listener (Prompt 130, Part B).

Standard library only. Accepts any method on any path and appends one record
per request to captures/<UTC yyyymmdd>.log (UTF-8): receive time (UTC), client
IP, method, path, headers, then the body, pretty-printed if it is JSON. For
multipart bodies each part's headers and size are logged, and image parts are
saved under captures/img/. Every request gets 200 {"ok": true}.

A capture tool only, not part of the backend. It refuses ports 8000-8003 (the
live SKYE server and tools/harness).

Secrets are never written: Authorization/Cookie header values are replaced by
their length, JSON values under credential-like keys are masked, and the URL
path from captures/secret_path.txt is logged as <SECRET_PATH>.

    python listener.py --new-path      # make a random 24-char path, print it, exit
    python listener.py [--port 8091]   # listen until Ctrl+C
"""
import argparse
import datetime as dt
import itertools
import json
import os
import re
import secrets
import string
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORBIDDEN_PORTS = range(8000, 8004)
MAX_BODY = 20 * 1024 * 1024      # larger bodies are truncated, not rejected
TEXT_PREVIEW = 64 * 1024          # non-JSON text bodies are logged up to this many chars
SOCKET_TIMEOUT_S = 10

SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie"}
SENSITIVE_KEY = re.compile(r"pass(word)?|passwd|pwd|token|stok|secret|credential|authoriz", re.I)
SENSITIVE_TEXT = re.compile(
    r"""(?P<k>pass(?:word)?|passwd|pwd|token|stok|secret)(?P<sep>["']?\s*[:=]\s*["']?)(?P<v>[^"'&\s,;}<]+)""",
    re.I,
)

_seq = itertools.count(1)
_write_lock = threading.Lock()
_captures: Path = HERE / "captures"
_secret_path: str = ""


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def _console(line: str) -> None:
    # ASCII only: the Windows console codepage can't take everything.
    try:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)
    except Exception:
        pass


def _write(recv: dt.datetime, text: str) -> None:
    path = _captures / f"{recv:%Y%m%d}.log"
    with _write_lock:
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write(text if text.endswith("\n") else text + "\n")


def _mask_path(path: str) -> str:
    if _secret_path and _secret_path in path:
        return path.replace(_secret_path, "<SECRET_PATH>")
    return path


def _redact_json(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and SENSITIVE_KEY.search(k) and isinstance(v, (str, int, float)):
                out[k] = f"<redacted {type(v).__name__} len={len(str(v))}>"
            else:
                out[k] = _redact_json(v)
        return out
    if isinstance(value, list):
        return [_redact_json(v) for v in value]
    return value


def _redact_text(text: str) -> str:
    return SENSITIVE_TEXT.sub(lambda m: f"{m['k']}{m['sep']}<redacted len={len(m['v'])}>", text)


def _shape(value, depth: int = 0) -> str:
    """Key structure of a JSON value, e.g. {ip:str, event_list:[{dateTime:str}]}."""
    if depth > 6:
        return "..."
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}:{_shape(v, depth + 1)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        shapes = []
        for v in value:
            s = _shape(v, depth + 1)
            if s not in shapes:
                shapes.append(s)
        return "[" + " | ".join(shapes) + f"] x{len(value)}"
    if value is None:
        return "null"
    return type(value).__name__


def _find_event_types(value, found: list) -> list:
    if isinstance(value, dict):
        for k, v in value.items():
            if k == "event_type":
                found.extend(v if isinstance(v, list) else [v])
            else:
                _find_event_types(v, found)
    elif isinstance(value, list):
        for v in value:
            _find_event_types(v, found)
    return found


def _try_json(data: bytes):
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return True, json.loads(data.decode(enc))
        except Exception:
            continue
    return False, None


def _ext_for(ctype: str, data: bytes) -> str:
    ctype = ctype.lower()
    if "png" in ctype or data[:4] == b"\x89PNG":
        return ".png"
    if "jpeg" in ctype or "jpg" in ctype or data[:2] == b"\xff\xd8":
        return ".jpg"
    return ".bin"


def _save_image(recv: dt.datetime, seq: int, idx: int, ctype: str, data: bytes) -> str:
    img_dir = _captures / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    name = f"{recv:%Y%m%dT%H%M%S}_{seq:05d}_{idx}{_ext_for(ctype, data)}"
    (img_dir / name).write_bytes(data)
    return f"img/{name}"


def _describe_content(recv, seq, idx, ctype: str, data: bytes, lines: list, events: list) -> None:
    """Append a description of one body (or one multipart part) to lines."""
    if not data:
        lines.append("(empty)")
        return
    is_image = ctype.lower().startswith("image/") or data[:2] == b"\xff\xd8" or data[:4] == b"\x89PNG"
    if is_image:
        try:
            saved = _save_image(recv, seq, idx, ctype, data)
            lines.append(f"(image, {len(data)} bytes, saved as {saved})")
        except Exception as e:
            lines.append(f"(image, {len(data)} bytes, save failed: {e!r})")
        return
    ok, obj = _try_json(data)
    if ok:
        events.extend(str(e) for e in _find_event_types(obj, []))
        red = _redact_json(obj)
        lines.append(f"json shape: {_shape(red)}")
        lines.append(json.dumps(red, indent=2, ensure_ascii=False))
        return
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        lines.append(f"(binary, {len(data)} bytes) first 256 bytes hex: {data[:256].hex()}")
        return
    shown = _redact_text(text[:TEXT_PREVIEW])
    lines.append("(text, not JSON)")
    lines.append(shown)
    if len(text) > TEXT_PREVIEW:
        lines.append(f"... truncated, {len(text) - TEXT_PREVIEW} more chars")


def _parse_headers_block(raw: str) -> list:
    out = []
    for line in raw.replace("\r\n", "\n").split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            out.append((k.strip(), v.strip()))
        elif line.strip():
            out.append(("(unparsed)", line.strip()))
    return out


def _describe_multipart(recv, seq, ctype: str, body: bytes, lines: list, events: list) -> bool:
    m = re.search(r'boundary="?([^";]+)"?', ctype, re.I)
    if not m:
        lines.append("(multipart without a boundary parameter)")
        return False
    boundary = m.group(1).strip()
    delim = b"--" + boundary.encode("latin-1", "replace")
    segments = body.split(delim)
    if len(segments) < 2:
        lines.append(f"(boundary {boundary!r} not found in the body)")
        return False
    lines.append(f"multipart boundary={boundary!r}")
    if segments[0].strip():
        lines.append(f"preamble: {len(segments[0])} bytes")
    closed = False
    idx = 0
    for seg in segments[1:]:
        if seg.startswith(b"--"):
            closed = True
            break
        idx += 1
        if seg.startswith(b"\r\n"):
            seg = seg[2:]
        elif seg.startswith(b"\n"):
            seg = seg[1:]
        if seg.endswith(b"\r\n"):
            seg = seg[:-2]
        elif seg.endswith(b"\n"):
            seg = seg[:-1]
        end, sep = seg.find(b"\r\n\r\n"), 4
        if end == -1:
            end, sep = seg.find(b"\n\n"), 2
        if end == -1:
            lines.append(f"-- part {idx}: no header/body separator, {len(seg)} bytes")
            continue
        headers = _parse_headers_block(seg[:end].decode("latin-1"))
        content = seg[end + sep:]
        part_ctype = next((v for k, v in headers if k.lower() == "content-type"), "")
        lines.append(f"-- part {idx}: {len(content)} bytes")
        for k, v in headers:
            lines.append(f"   {k}: {v}")
        _describe_content(recv, seq, idx, part_ctype, content, lines, events)
    lines.append(f"parts: {idx}, closing delimiter: {'yes' if closed else 'no'}")
    return True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "vigi-listener"
    sys_version = ""
    timeout = SOCKET_TIMEOUT_S

    def log_message(self, fmt, *args):  # the capture file replaces the stderr access log
        pass

    def handle(self):
        # Every TCP connection is recorded, so a client that connects and
        # closes (or stalls) without sending a request still leaves a trace.
        self._requests_seen = 0
        opened = _utcnow()
        ip, port = self.client_address[0], self.client_address[1]
        try:
            _write(opened, f"---- connection opened  {_iso(opened)}  from {ip}:{port}\n")
            _console(f"{_iso(opened)} {ip}:{port} connection opened")
        except Exception:
            pass
        try:
            super().handle()
        finally:
            if self._requests_seen == 0:
                closed = _utcnow()
                secs = (closed - opened).total_seconds()
                try:
                    _write(closed, f"---- connection from {ip}:{port} closed after {secs:.1f} s "
                                   f"without a complete HTTP request\n")
                    _console(f"{_iso(closed)} {ip}:{port} closed without a request ({secs:.1f} s)")
                except Exception:
                    pass

    def __getattr__(self, name):
        # Any method (POST, PUT, GET, or something unusual) goes to _handle.
        if name.startswith("do_"):
            return self._handle
        raise AttributeError(name)

    def send_error(self, code, message=None, explain=None):
        # Malformed request lines end up here; record them, then answer as usual.
        self._requests_seen = getattr(self, "_requests_seen", 0) + 1
        try:
            recv = _utcnow()
            raw = getattr(self, "raw_requestline", b"")[:300]
            _write(recv, f"==== malformed request  {_iso(recv)}  from {self.client_address[0]}  "
                         f"-> {code} {message or ''}\n   raw request line: {raw!r}\n")
            _console(f"{_iso(recv)} {self.client_address[0]} malformed request -> {code}")
        except Exception:
            pass
        try:
            super().send_error(code, message, explain)
        except Exception:
            pass

    def _read_exact(self, n: int) -> bytes:
        # Keeps whatever arrived if the client stalls or disconnects early.
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = self.rfile.read1(n - len(buf))
            except OSError:
                self.close_connection = True
                break
            if not chunk:
                break
            buf += chunk
        return bytes(buf)

    def _read_chunked(self) -> bytes:
        out = bytearray()
        while True:
            line = self.rfile.readline(1024)
            if not line:
                break
            size = int(line.split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while self.rfile.readline(1024) not in (b"\r\n", b"\n", b""):
                    pass
                break
            take = min(size, MAX_BODY - len(out))
            out += self._read_exact(take)
            if take < size:
                self.close_connection = True
                break
            self.rfile.readline(8)
        return bytes(out)

    def _read_body(self):
        te = (self.headers.get("Transfer-Encoding") or "").lower()
        cl = self.headers.get("Content-Length")
        if "chunked" in te:
            return self._read_chunked(), "chunked"
        if cl is None:
            return b"", "no Content-Length"
        try:
            n = int(cl)
        except ValueError:
            self.close_connection = True
            return b"", f"invalid Content-Length {cl!r}"
        take = max(0, min(n, MAX_BODY))
        data = self._read_exact(take)
        note = f"Content-Length {n}"
        if len(data) < take:
            note += f", only {len(data)} bytes arrived"
            self.close_connection = True
        if n > MAX_BODY:
            note += f", truncated to {MAX_BODY}"
            self.close_connection = True
        return data, note

    def _handle(self):
        self._requests_seen = getattr(self, "_requests_seen", 0) + 1
        recv = _utcnow()
        seq = next(_seq)
        events: list = []
        body, body_note = b"", ""
        try:
            body, body_note = self._read_body()
        except Exception as e:
            body_note = f"body read failed: {e!r}"
            self.close_connection = True
        try:
            record = self._format(recv, seq, body, body_note, events)
        except Exception:
            record = (f"==== #{seq}  {_iso(recv)}  from {self.client_address[0]}\n"
                      f"(formatting failed)\n{traceback.format_exc()}")
        try:
            _write(recv, record)
        except Exception as e:
            _console(f"#{seq} WRITE FAILED: {e!r}")
        ctype = (self.headers.get("Content-Type") or "-").split(";")[0]
        _console(f"#{seq} {_iso(recv)} {self.client_address[0]} {self.command} "
                 f"{_mask_path(self.path)} {len(body)}B {ctype}"
                 + (f" event_type={events}" if events else ""))
        # One request per connection: the VIGI camera opens a new connection
        # per event and resets it ~0.5 s after our reply. Waiting on the
        # connection for a second request only turned that reset into a
        # ConnectionResetError traceback per event (664 of them on 5 Oct).
        self.close_connection = True
        try:
            payload = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except Exception:
            self.close_connection = True

    def _format(self, recv, seq, body: bytes, body_note: str, events: list) -> str:
        path = _mask_path(self.path)
        match = "yes" if _secret_path and _secret_path in self.path else "no"
        lines = [
            f"==== #{seq}  {_iso(recv)}  from {self.client_address[0]}:{self.client_address[1]}",
            f"{self.command} {path} {self.request_version}   (secret path: {match})",
            "-- headers",
        ]
        for k, v in self.headers.items():
            if k.lower() in SENSITIVE_HEADERS:
                v = f"<redacted len={len(v)}>"
            lines.append(f"{k}: {v}")
        ctype = self.headers.get("Content-Type") or ""
        lines.append(f"-- body: {len(body)} bytes ({body_note}), Content-Type: {ctype or '(none)'}")
        if body:
            if ctype.lower().startswith("multipart/"):
                if not _describe_multipart(recv, seq, ctype, body, lines, events):
                    _describe_content(recv, seq, 0, "", body, lines, events)
            else:
                _describe_content(recv, seq, 0, ctype, body, lines, events)
        if events:
            lines.append(f"-- event_type values: {events}")
        return "\n".join(lines) + "\n"


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False   # on Windows SO_REUSEADDR would let two processes share the port

    def handle_error(self, request, client_address):
        try:
            recv = _utcnow()
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
                _write(recv, f"---- connection from {client_address[0]} reset by the client: {type(exc).__name__}\n")
            else:
                _write(recv, f"==== handler error  {_iso(recv)}  from {client_address[0]}\n{traceback.format_exc()}")
        except Exception:
            pass


def _new_path() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))


def main() -> int:
    global _captures, _secret_path
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--captures-dir", default=str(HERE / "captures"),
                    help="where logs, images and secret_path.txt live (default: ./captures)")
    ap.add_argument("--new-path", action="store_true",
                    help="write a new random 24-char URL path to secret_path.txt, print it and exit")
    args = ap.parse_args()

    if args.port in FORBIDDEN_PORTS:
        print(f"refusing port {args.port}: 8000-8003 belong to the SKYE server and tools/harness")
        return 2

    _captures = Path(args.captures_dir).resolve()
    _captures.mkdir(parents=True, exist_ok=True)
    secret_file = _captures / "secret_path.txt"

    if args.new_path:
        path = _new_path()
        secret_file.write_text(path + "\n", encoding="utf-8")
        print(f"/{path}")
        return 0

    if secret_file.exists():
        _secret_path = secret_file.read_text(encoding="utf-8").strip()

    srv = Server((args.host, args.port), Handler)
    (_captures / "listener.pid").write_text(str(os.getpid()), encoding="utf-8")
    start = _utcnow()
    _write(start, f"#### listener started {_iso(start)} on {args.host}:{args.port} pid={os.getpid()} "
                  f"secret path loaded: {'yes' if _secret_path else 'no'}\n")
    _console(f"listening on {args.host}:{args.port}, writing to {_captures}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop = _utcnow()
        _write(stop, f"#### listener stopped {_iso(stop)}\n")
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
