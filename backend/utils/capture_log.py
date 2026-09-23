"""
Durable capture log (Prompt 128).

Tees everything the backend worker writes to stdout/stderr — print() output
such as the [OMADA] dump and [MEMBERSHIP-128], the root logger, and uvicorn's
own access/error loggers — into a UTF-8 file under backend/logs/, while the
console keeps receiving exactly what it did before. (Under --reload the
supervisor process's few lines, e.g. "WatchFiles detected changes", stay
console-only: it never imports main.py.)

Why: until now a field capture only reached disk if the operator remembered
to pipe stdout through PowerShell's Tee-Object, which also wrote UTF-16LE.
That is how the 10 Sep calibration log was lost. Stdlib only, so main.py can
install it before any other app import.
"""
import atexit
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# With OMADA_RAW_DUMP_ENABLED=true and 3 APs at ~1 Hz the log grows ~10 KB/s
# (~36 MB/h), so one part comfortably holds a whole field session.
_MAX_BYTES = 50 * 1024 * 1024

# At most one capture-failure warning per this many seconds on the console.
_WARNING_INTERVAL_S = 60.0

# uvicorn colours its console output when stdout is a terminal; keep the
# escape codes out of the file.
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

# Set while a thread is inside the capture path, shared by BOTH tees: the
# file handler's error path, or anything else it prints, must never be
# captured again, whichever stream it lands on.
_capturing = threading.local()

_installed_path: Optional[Path] = None


class _PartFileHandler(RotatingFileHandler):
    """Size-rotated, but by starting a new part file (skye-<ts>.part002.log,
    ...) instead of renaming the full one. Windows can't rename a file that
    another process has open (WinError 32 — e.g. an analysis script reading
    the live capture), and when the stock rename fails it drops records and
    its retries shift older backups off the end. Nothing is ever renamed or
    deleted here."""

    def __init__(self, path: Path, max_bytes: int, console) -> None:
        self._first_path = path
        self._part = 1
        self._console = console  # the original, un-teed stderr
        self._last_warning = 0.0
        super().__init__(path, maxBytes=max_bytes, encoding="utf-8", errors="backslashreplace")

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        self._part += 1
        self.baseFilename = str(
            self._first_path.with_name(f"{self._first_path.stem}.part{self._part:03d}{self._first_path.suffix}")
        )
        self.stream = self._open()

    def handleError(self, record: logging.LogRecord) -> None:
        # The stock handleError prints a full traceback to sys.stderr — the
        # tee — once per failed line. Say it once a minute, on the real
        # console, and carry on: the console itself is unaffected.
        now = time.monotonic()
        if now - self._last_warning < _WARNING_INTERVAL_S:
            return
        self._last_warning = now
        try:
            self._console.write(
                f"[CAPTURE-128] WARNING: could not write to {self.baseFilename}: "
                f"{sys.exc_info()[1]!r} (console output unaffected)\n"
            )
            self._console.flush()
        except Exception:
            pass


class _Tee:
    """Wraps a text stream. Every write goes to the wrapped stream unchanged;
    each complete line is also handed to the capture handler. Partial lines
    are buffered per thread, so lines printed concurrently from the ingest
    threadpool don't interleave mid-line in the file."""

    def __init__(self, stream, handler: logging.Handler) -> None:
        self._stream = stream
        self._handler = handler
        self._pending = threading.local()

    def write(self, s: str) -> int:
        n = self._stream.write(s)
        if not getattr(_capturing, "active", False):
            _capturing.active = True
            try:
                self._capture(s)
            except Exception:
                pass  # capture must never break console output
            finally:
                _capturing.active = False
        return n

    def writelines(self, lines) -> None:
        for line in lines:
            self.write(line)

    def _capture(self, s: str) -> None:
        pending = getattr(self._pending, "text", "") + s
        *lines, self._pending.text = pending.split("\n")
        for line in lines:
            self._emit(line)

    def _emit(self, line: str) -> None:
        record = logging.makeLogRecord({
            "msg": _ANSI_ESCAPE.sub("", line.rstrip("\r")),
            "levelno": logging.INFO,
            "levelname": "INFO",
        })
        self._handler.handle(record)

    def flush_pending(self) -> None:
        """Write out this thread's unterminated line, if any (called at exit)."""
        pending = getattr(self._pending, "text", "")
        if pending:
            self._pending.text = ""
            self._emit(pending)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        # encoding, isatty, fileno, reconfigure, buffer, ... of the real stream
        return getattr(self._stream, name)


def install_capture_log(log_dir: Path) -> Optional[Path]:
    """Start teeing stdout/stderr into log_dir/skye-<UTC yyyymmdd-HHMMSS>.log.
    Idempotent per process: `python main.py` imports main.py twice (as
    __main__, then as main:app), and the second call returns the first path.
    Returns None, with a console warning and the console untouched, if the
    file can't be opened — like Prompt 126's reconfigure, this must never be
    what stops the backend starting."""
    global _installed_path
    if _installed_path is not None:
        return _installed_path

    old_out, old_err = sys.stdout, sys.stderr
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = log_dir / f"skye-{stamp}.log"
        if path.exists():  # two processes started within the same second
            path = log_dir / f"skye-{stamp}-{os.getpid()}.log"

        # utf-8 writes no BOM. Flushed after every line (StreamHandler.emit),
        # so a killed process loses at most the line it was halfway through.
        handler = _PartFileHandler(path, _MAX_BYTES, old_err)
    except Exception as e:
        print(f"[CAPTURE-128] WARNING: capture log disabled, console only: {e}", file=sys.stderr)
        return None

    formatter = logging.Formatter("%(asctime)s.%(msecs)03dZ %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)

    tee_out, tee_err = _Tee(old_out, handler), _Tee(old_err, handler)
    sys.stdout, sys.stderr = tee_out, tee_err

    # uvicorn configures its loggers before importing main:app, so their
    # StreamHandlers already hold the original stream objects and would
    # bypass the tee. Re-point every handler that writes to either stream.
    loggers = [logging.getLogger()] + [
        lg for lg in logging.Logger.manager.loggerDict.values() if isinstance(lg, logging.Logger)
    ]
    for lg in loggers:
        for h in lg.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                if h.stream is old_out:
                    h.setStream(tee_out)
                elif h.stream is old_err:
                    h.setStream(tee_err)

    # Registered after logging's own atexit shutdown, so it runs first (LIFO)
    # and the last partial line lands before the handler is closed.
    atexit.register(tee_out.flush_pending)
    atexit.register(tee_err.flush_pending)

    _installed_path = path
    print(f"[CAPTURE-128] writing console output to {path}")
    return path
