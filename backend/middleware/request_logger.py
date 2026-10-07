import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from utils.log_redaction import redact_path

logger = logging.getLogger(__name__)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Log every request method, path, and response time in milliseconds.
    Paths under /vigi/alarm/ are logged as /vigi/alarm/*** (the path segment is
    the camera's credential - Prompt 131 T5)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info("[%s] %s  %.1fms", request.method, redact_path(request.url.path), elapsed_ms)
        return response
