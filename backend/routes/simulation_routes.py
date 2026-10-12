"""
Simulation routes — start/stop/status for patrol, events, and shift simulations.

POST /simulation/start?mode=patrol   → runs simulation_patrol.py
POST /simulation/start?mode=events   → runs simulation_events.py (default)
POST /simulation/start?mode=shift    → runs simulation_shift.py
POST /simulation/stop                → stops whichever is running
GET  /simulation/status              → returns running/stopped + current mode
"""
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from middleware.auth_middleware import require_admin, require_auth
from models.user import UserRecord
from services.simulation_patrol import run_simulation as run_patrol
from services.simulation_events import run_simulation as run_events
from services.simulation_shift  import run_simulation as run_shift

router = APIRouter(tags=["simulation"])

_task: Optional[asyncio.Task] = None
_current_mode: Optional[str] = None


def _is_running() -> bool:
    return _task is not None and not _task.done()


async def cancel_running_simulation(timeout: float = 8.0) -> bool:
    """Cancel a running simulation and wait up to `timeout` seconds for it to
    end, so its finally block removes its people from /positions. Called by
    main.py's lifespan on shutdown and on every --reload (Prompt 135, CON-04).
    asyncio.wait, not wait_for: on a timeout wait_for would cancel the task a
    second time and cut its clean-up short. True if a simulation was running."""
    global _task, _current_mode
    task = _task
    if task is None or task.done():
        return False
    task.cancel()
    done, _pending = await asyncio.wait({task}, timeout=timeout)
    if not done:
        logging.warning("[SIM] the running simulation didn't stop within %.0f s of shutdown", timeout)
    elif not task.cancelled():
        task.exception()   # retrieved, so asyncio doesn't warn that it never was
    _task = None
    _current_mode = None
    return True


@router.post("/simulation/start")
async def start_simulation(
    mode: str = Query(default="events", pattern="^(patrol|events|shift)$"),
    admin: UserRecord = Depends(require_admin),
):
    global _task, _current_mode

    if _is_running():
        raise HTTPException(
            status_code=400,
            detail=f"Simulation already running in '{_current_mode}' mode. Stop it first.",
        )

    _current_mode = mode
    if mode == "patrol":
        runner = run_patrol
    elif mode == "shift":
        runner = run_shift
    else:
        runner = run_events
    _task = asyncio.create_task(runner())

    return {"status": "started", "mode": mode}


@router.post("/simulation/stop")
async def stop_simulation(admin: UserRecord = Depends(require_admin)):
    global _task, _current_mode

    if not _is_running():
        raise HTTPException(status_code=400, detail="No simulation is currently running.")

    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass

    stopped_mode = _current_mode
    _task = None
    _current_mode = None

    return {"status": "stopped", "mode": stopped_mode}


@router.get("/simulation/status")
async def simulation_status(caller: UserRecord = Depends(require_auth)):
    return {
        "running": _is_running(),
        "mode": _current_mode if _is_running() else None,
    }
