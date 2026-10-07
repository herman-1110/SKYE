"""
Beacon → person identity registry for the Omada RSSI ingestion path.

Beacons are identified by their stable iBeacon identity: UUID + major + minor.
This survives BLE MAC randomization (phones rotate their MAC; the iBeacon
identifiers stay constant). Real Minew beacons also broadcast iBeacon identifiers.

Key format: "<uuid_lowercase>:<major>:<minor>"
  e.g. "c001405c0e9f43b8af4aea309ba7e130:0001:0001"
"""
from typing import Dict, Optional, TypedDict


class BeaconIdentity(TypedDict, total=False):
    person_id: str
    person_type: str  # "guard" | "worker" | "forklift"
    label: str
    tx_power: float   # optional — _refresh_beacon_cache populates it; legacy seed may omit


def make_ibeacon_key(uuid: str, major: str, minor: str) -> str:
    """Build the composite identity key from iBeacon fields (uuid lowercased)."""
    return f"{(uuid or '').lower()}:{major}:{minor}"


# Legacy seed only — migrated into Firestore on startup (idempotent), then vestigial.
# iBeacon identity key → person identity
#
# Empty by design: the one entry that used to live here (the nRF Connect test
# phone, "Guard Alpha (Real)") was deleted from the live registry on purpose.
# seed_from_legacy() re-creates anything listed here that's missing from
# Firestore — it can't tell "never seeded" apart from "deleted on purpose" —
# so a deleted beacon must also be removed from this dict, or it comes back
# on every restart. Don't re-add it; register beacons via the dashboard/API
# instead, which is the actual source of truth now.
SEED_BEACONS: Dict[str, BeaconIdentity] = {}

# resolve_beacon_by_ibeacon() removed — see OmadaIngestService._resolve_beacon (cached)
