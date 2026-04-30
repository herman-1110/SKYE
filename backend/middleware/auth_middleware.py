from functools import wraps
from typing import Any, Callable

from flask import jsonify, request

from config.settings import settings


def require_omada_token(f: Callable) -> Callable:
    """Decorator that validates the Omada Bearer token on incoming telemetry requests."""
    @wraps(f)
    def _decorated(*args: Any, **kwargs: Any) -> Any:
        token = request.headers.get("Authorization", "")
        if token != f"Bearer {settings.OMADA_ACCESS_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return _decorated
