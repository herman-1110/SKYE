import logging

from flask import Flask, request

logger = logging.getLogger(__name__)


def register_request_logger(app: Flask) -> None:
    """Log every incoming request method, path, remote address, and timestamp."""

    @app.before_request
    def _log() -> None:
        logger.info("[%s] %s  from=%s", request.method, request.path, request.remote_addr)
