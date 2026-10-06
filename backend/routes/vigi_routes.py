from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from services.vigi_service import vigi_service
from utils.limiter import limiter

router = APIRouter(tags=["vigi"])


# The camera's Alarm Server posts here (Prompt 131 T4). No /api prefix (Next.js
# rewrites /api/* to the backend; the camera talks to :8000 directly), like
# /telemetry/omada. The camera can't send an auth header, so the path segment
# is the credential: VIGI_ALARM_PATH_SECRET, checked in constant time. A wrong
# or unset secret gets exactly what an unknown route gets. Logged paths under
# /vigi/alarm/ are always redacted (utils/log_redaction.py).
#
# The work runs in a worker thread and never under
# positioning_service.pipeline_lock. Every accepted request is answered
# 200 {"ok": true} with Connection: close - the camera opens a new connection
# per event and resets it after the reply, and a 200 stops it retrying.
@router.post("/vigi/alarm/{path_secret}", include_in_schema=False)
@limiter.limit("600/minute")
async def vigi_alarm(request: Request, path_secret: str) -> JSONResponse:
    if not vigi_service.path_secret_ok(path_secret):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    received_at = datetime.now(timezone.utc)
    raw = await request.body()
    source_ip = request.client.host if request.client else ""
    await run_in_threadpool(
        vigi_service.handle_alarm, raw, request.headers.get("content-type", ""), source_ip, received_at,
    )
    return JSONResponse(content={"ok": True}, headers={"Connection": "close"})
