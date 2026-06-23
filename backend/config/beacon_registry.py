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
SEED_BEACONS: Dict[str, BeaconIdentity] = {
    # Test phone (nRF Connect iBeacon) — Guard Alpha
    "c001405c0e9f43b8af4aea309ba7e130:0001:0001": {
        "person_id": "guard-001",
        "person_type": "guard",
        "label": "Guard Alpha (Real)",
    },
}

# resolve_beacon_by_ibeacon() removed — see OmadaIngestService._resolve_beacon (cached)
