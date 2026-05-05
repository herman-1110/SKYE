import logging

import firebase_admin
from firebase_admin import credentials
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from middleware.error_handler import register_exception_handlers
from middleware.request_logger import RequestLoggerMiddleware
from routes.alert_routes import router as alert_router
from routes.floor_plan_routes import router as floor_plan_router
from routes.report_routes import router as report_router
from routes.telemetry_routes import router as telemetry_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
    # databaseURL is required for Realtime Database; Firestore uses the same app via firestore.client()
    firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_RTDB_URL})

    app = FastAPI(title="SKYE Sentinel-AI", version="0.1.0")

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(RequestLoggerMiddleware)

    register_exception_handlers(app)

    app.include_router(telemetry_router)
    app.include_router(alert_router)
    app.include_router(report_router)
    app.include_router(floor_plan_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
