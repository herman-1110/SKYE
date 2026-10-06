"""Keep the VIGI alarm path secret out of every log line (Prompt 131 A1/T5).

The camera posts to /vigi/alarm/<VIGI_ALARM_PATH_SECRET>, so the request path
itself is the credential. Three places log request paths:

- uvicorn's access log ("uvicorn.access"): the path is record.args[2] of
  '%s - "%s %s HTTP/%s" %d' (uvicorn/protocols/http/h11_impl.py and
  httptools_impl.py). AccessFormatter unpacks those five args, so each arg is
  redacted in place and the tuple keeps its shape.
- middleware/request_logger.py, which also calls redact_path() itself.
- slowapi: with its default key_style="url" it logs "ratelimit ... exceeded
  at endpoint: <path>" on the "slowapi" logger when a limit trips.

Everything under /vigi/alarm/ is redacted by prefix, not by matching the real
secret, so a wrong guess in a 404 line is hidden too. The filter is attached
to those loggers and to every handler that exists when it's installed
(root's and uvicorn's), which also covers propagated records, tracebacks
(exc_text) and stack info. A filter that raised would make logging print the
raw record through Handler.handleError, so any error here drops the record
instead.
"""
import logging
import re

REDACTED_ALARM_PATH = "/vigi/alarm/***"
_ALARM_PATH = re.compile(r"/vigi/alarm/[^\s\"'<>]*", re.IGNORECASE)
_MARKER = "/vigi/alarm/"

_LOGGERS = ("uvicorn.access", "uvicorn.error", "uvicorn", "slowapi", "middleware.request_logger", "")


def redact_path(text: str) -> str:
    """Replace every /vigi/alarm/<anything> (query string included) with
    /vigi/alarm/***."""
    if _MARKER not in text.lower():
        return text
    return _ALARM_PATH.sub(REDACTED_ALARM_PATH, text)


def _redact_value(value):
    if isinstance(value, str):
        return redact_path(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    # URL objects, scopes, exceptions: only replaced if their text holds the
    # path. An arg whose __str__ raises is left alone rather than dropping a
    # whole unrelated record (Prompt 126's A6 case).
    try:
        text = str(value)
    except Exception:
        return value
    return redact_path(text) if _MARKER in text.lower() else value


class AlarmPathRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_path(record.msg)
            elif record.msg is not None:
                record.msg = _redact_value(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(_redact_value(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: _redact_value(v) for k, v in record.args.items()}
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = redact_path(record.exc_text)
            if record.stack_info:
                record.stack_info = redact_path(record.stack_info)
            return True
        except Exception:
            return False


_FILTER = AlarmPathRedactionFilter()


def install_log_redaction() -> None:
    """Attach the filter to the path-logging loggers and to every handler they
    (and root) have now. Idempotent. Call after logging is configured."""
    for name in _LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, AlarmPathRedactionFilter) for f in logger.filters):
            logger.addFilter(_FILTER)
        for handler in logger.handlers:
            if not any(isinstance(f, AlarmPathRedactionFilter) for f in handler.filters):
                handler.addFilter(_FILTER)
