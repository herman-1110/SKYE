import logging

import firebase_admin
from firebase_admin import credentials
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import settings
from middleware.error_handler import register_exception_handlers
from middleware.request_logger import RequestLoggerMiddleware
from routes.alert_routes import router as alert_router
from routes.auth_routes import router as auth_router
from routes.beacon_routes import router as beacon_router
from routes.building_routes import router as building_router
from routes.floor_routes import router as floor_router
from routes.report_routes import router as report_router
from routes.safety_settings_routes import router as safety_settings_router
from routes.telemetry_routes import router as telemetry_router
from routes.omada_telemetry import router as omada_telemetry_router
from routes.simulation_routes import router as simulation_router
from routes.user_routes import router as user_router
from routes.vigi_routes import router as vigi_router
from routes.zone_routes import router as zone_router
from utils.limiter import limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

_MAX_BODY_BYTES = 1_048_576  # 1 MB


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Payload too large"})
        return await call_next(request)


def create_app() -> FastAPI:
    cred = credentials.Certificate(settings.FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {"databaseURL": settings.FIREBASE_RTDB_URL})

    # Idempotently migrate the hardcoded beacon seed into Firestore.
    from repositories.beacon_repository import beacon_repository
    seeded = beacon_repository.seed_from_legacy()
    if seeded:
        logging.info("[SEED] migrated %d legacy beacon(s) into Firestore", seeded)

    # Idempotently seed the safety-settings doc from settings.py defaults.
    from repositories.safety_settings_repository import safety_settings_repository
    safety_settings_repository.seed_defaults()

    app = FastAPI(title="SKYE Sentinel-AI", version="0.1.0")

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # CORS — restricted to local dev origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.add_middleware(MaxBodySizeMiddleware)
    app.add_middleware(RequestLoggerMiddleware)

    register_exception_handlers(app)

    # Public
    app.include_router(auth_router)

    # Omada-token protected
    app.include_router(telemetry_router)
    app.include_router(omada_telemetry_router)

    # Firebase-token protected
    app.include_router(alert_router)
    app.include_router(beacon_router)
    app.include_router(building_router)
    app.include_router(floor_router)
    app.include_router(zone_router)
    app.include_router(report_router)
    app.include_router(safety_settings_router)
    app.include_router(user_router)
    app.include_router(simulation_router)
    app.include_router(vigi_router)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
