import asyncio
from fastapi import APIRouter

from services.simulation_service import run_simulation

router = APIRouter(tags=["simulation"])

_sim_task: asyncio.Task | None = None


@router.post("/simulation/start")
async def start_simulation() -> dict:
    global _sim_task
    if _sim_task is not None and not _sim_task.done():
        return {"status": "already_running"}
    _sim_task = asyncio.create_task(run_simulation())
    return {"status": "started"}


@router.post("/simulation/stop")
async def stop_simulation() -> dict:
    global _sim_task
    if _sim_task is not None and not _sim_task.done():
        _sim_task.cancel()
        _sim_task = None
        return {"status": "stopped"}
    return {"status": "not_running"}


@router.get("/simulation/status")
async def simulation_status() -> dict:
    if _sim_task is None:
        return {"status": "not_started"}
    if _sim_task.done():
        exc = _sim_task.exception() if not _sim_task.cancelled() else None
        return {"status": "stopped", "error": str(exc) if exc else None}
    return {"status": "running"}
