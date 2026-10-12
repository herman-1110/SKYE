"""Removing simulated people from RTDB /positions (Prompt 135, COR-05 / CON-04).

The simulators post to /telemetry with each simulated beacon's fixed MAC as
reporter_mac, so their records sit at /positions/AA_BB_CC_DD_EE_0N. Real
positions are keyed by person_id (/positions/guard-001), so the two can't
collide. A record left behind after a simulation stops goes stale and makes
the signal-loss sweep raise a false man-down, and a simulated forklift stays
in every collision check.

- Each simulator removes its own people's records in a finally block, so a
  stop, an error or a cancel all clean up (simulation_*.run_simulation).
- main.py's lifespan cancels a running simulation on shutdown and reload, so
  that finally block also runs then, and removes every simulator's records at
  startup, before the signal-loss loop starts: anything found then is a
  leftover from a hard kill.

The Firebase calls run in a worker thread and are waited for at most
CLEANUP_TIMEOUT_S; a failure or a timeout is logged and never raised.
"""
import asyncio
import logging
from typing import Iterable, List, Optional

from firebase_admin import db as rtdb

log = logging.getLogger(__name__)

CLEANUP_TIMEOUT_S = 5.0


def position_keys(beacons: Iterable[dict]) -> List[str]:
    """The /positions keys a simulator's beacons write: the MAC with '_'."""
    return [b["mac"].replace(":", "_") for b in beacons]


def all_simulated_position_keys() -> List[str]:
    """Every key any of the three simulators writes."""
    from services import simulation_events, simulation_patrol, simulation_shift
    keys = set(position_keys(simulation_events.SIMULATED_BEACONS))
    keys.update(position_keys(simulation_patrol.SIMULATED_BEACONS))
    keys.update(position_keys(simulation_shift.OUTGOING_BEACONS + simulation_shift.INCOMING_BEACONS))
    return sorted(keys)


def delete_positions(keys: Iterable[str]) -> int:
    """Blocking. Delete /positions/<key> for each given key that exists and
    return how many did. One read of /positions, then one delete per record."""
    keys = list(keys)
    if not keys:
        return 0
    current = rtdb.reference("/positions").get() or {}
    if not isinstance(current, dict):
        return 0
    present = [k for k in keys if k in current]
    for key in present:
        rtdb.reference(f"/positions/{key}").delete()
    return len(present)


async def remove_positions(keys: Iterable[str], who: str, timeout: Optional[float] = None) -> int:
    """delete_positions() in a worker thread, waited for at most `timeout`
    seconds (default CLEANUP_TIMEOUT_S). Never raises: safe in a finally block
    and in the lifespan. Returns how many records were removed (0 on failure)."""
    keys = list(keys)
    limit = CLEANUP_TIMEOUT_S if timeout is None else timeout
    try:
        removed = await asyncio.wait_for(asyncio.to_thread(delete_positions, keys), limit)
    except asyncio.TimeoutError:
        log.warning("[SIM] %s: removing simulated positions took longer than %.0f s; carrying on", who, limit)
        return 0
    except Exception as e:
        log.warning("[SIM] %s: removing simulated positions failed (%s); carrying on", who, type(e).__name__)
        return 0
    if removed:
        log.info("[SIM] %s: removed %d simulated position record(s)", who, removed)
    return removed
