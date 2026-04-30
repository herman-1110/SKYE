import logging

import firebase_admin
from firebase_admin import credentials
from flask import Flask

from config.settings import settings
from middleware.error_handler import register_error_handlers
from middleware.request_logger import register_request_logger
from routes.alert_routes import alert_bp
from routes.report_routes import report_bp
from routes.telemetry_routes import telemetry_bp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> Flask:
    cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_DATABASE_URL})

    app = Flask(__name__)
    register_request_logger(app)
    register_error_handlers(app)

    app.register_blueprint(telemetry_bp)
    app.register_blueprint(alert_bp)
    app.register_blueprint(report_bp)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=settings.PORT, debug=settings.DEBUG)
