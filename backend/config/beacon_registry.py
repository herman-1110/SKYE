"""
Beacon → person identity registry for the Omada RSSI ingestion path.

Beacons are identified by their stable iBeacon identity: UUID + major + minor.
This survives BLE MAC randomization (phones rotate their MAC; the iBeacon
identifiers stay constant). Real Minew beacons also broadcast iBeacon identifiers.

Key format: "<uuid_lowercase>:<major>:<minor>"
  e.g. "c001405c0e9f43b8af4aea309ba7e130:0001:0001"
"""
from typing import Dict, Optional, TypedDict


class BeaconIdentity(TypedDict):
    person_id: str
    person_type: str  # "guard" | "worker" | "forklift"
    label: str


def make_ibeacon_key(uuid: str, major: str, minor: str) -> str:
    """Build the composite identity key from iBeacon fields (uuid lowercased)."""
    return f"{(uuid or '').lower()}:{major}:{minor}"


# iBeacon identity key → person identity
REAL_BEACON_REGISTRY: Dict[str, BeaconIdentity] = {
    # Test phone (nRF Connect iBeacon) — Guard Alpha
    "c001405c0e9f43b8af4aea309ba7e130:0001:0001": {
        "person_id": "guard-001",
        "person_type": "guard",
        "label": "Guard Alpha (Real)",
    },
    # Add more beacons here:
    #   make_ibeacon_key(uuid, major, minor): {"person_id": ..., "person_type": ..., "label": ...}
}


def resolve_beacon_by_ibeacon(uuid: str, major: str, minor: str) -> Optional[BeaconIdentity]:
    """Return identity for an iBeacon (uuid/major/minor), or None if unregistered."""
    return REAL_BEACON_REGISTRY.get(make_ibeacon_key(uuid, major, minor))
