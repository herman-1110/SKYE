import traceback

from flask import Flask, Response, jsonify


def register_error_handlers(app: Flask) -> None:
    """Attach global error handlers that log full tracebacks and return safe JSON responses."""

    @app.errorhandler(400)
    def bad_request(e: Exception) -> Response:
        return jsonify({"error": "Bad request", "detail": str(e)}), 400

    @app.errorhandler(401)
    def unauthorized(e: Exception) -> Response:
        return jsonify({"error": "Unauthorized"}), 401

    @app.errorhandler(404)
    def not_found(e: Exception) -> Response:
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(Exception)
    def unhandled(e: Exception) -> Response:
        app.logger.error("Unhandled exception:\n%s", traceback.format_exc())
        return jsonify({"error": "Internal server error"}), 500
