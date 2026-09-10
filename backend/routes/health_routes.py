"""Read-only diagnostic surface (Prompt 126). No router-level prefix — matches
the sibling unprefixed routers (telemetry, omada-telemetry, simulation, vigi);
critical invariant, do not add /api.
"""
from fastapi import APIRouter, Depends

from middleware.auth_middleware import require_auth
from models.user import UserRecord
from services.safety_service import safety_service

router = APIRouter(tags=["health"])


@router.get("/health/tracker")
async def tracker_health(caller: UserRecord = Depends(require_auth)) -> dict:
    """Patrol-tracker invocation health. See safety_service._TrackerHealth's
    docstring for how to read the three states (throwing / upstream failure
    before the tracker runs / no ingest reaching it at all)."""
    return safety_service.get_tracker_health()
