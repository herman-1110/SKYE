import logging

import firebase_admin
from firebase_admin import credentials
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from middleware.error_handler import register_exception_handlers
from middleware.request_logger import RequestLoggerMiddleware
from routes.alert_routes import router as alert_router
from routes.auth_routes import router as auth_router
from routes.building_routes import router as building_router
from routes.floor_plan_routes import router as floor_plan_router
from routes.floor_routes import router as floor_router
from routes.report_routes import router as report_router
from routes.telemetry_routes import router as telemetry_router
from routes.user_routes import router as user_router
from routes.zone_routes import router as zone_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_RTDB_URL})

    app = FastAPI(title="SKYE Sentinel-AI", version="0.1.0")

    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(RequestLoggerMiddleware)

    register_exception_handlers(app)

    # Public
    app.include_router(auth_router)

    # Omada-token protected
    app.include_router(telemetry_router)

    # Firebase-token protected
    app.include_router(alert_router)
    app.include_router(building_router)
    app.include_router(floor_router)
    app.include_router(floor_plan_router)  # legacy — kept for existing data
    app.include_router(zone_router)
    app.include_router(report_router)
    app.include_router(user_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
