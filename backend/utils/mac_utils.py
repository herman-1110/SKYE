"""Camera MAC normalisation (Prompt 131).

One function for every camera MAC that enters the system: the cctv registry
(floor_routes / cctv_service), the alarm endpoint (vigi_service) and the
heartbeat writer (cctv_repository.update_heartbeat). The real InSight S445
sends "98-ba-5f-8b-10-03" in its alarm payload, OpenAPI's getDeviceInfo
returns "98-BA-5F-8B-10-03", and the registry and dashboard use
"98:BA:5F:8B:10:03" - all three must land on the same value.

AP MACs keep their own, older validator in floor_routes.py; this module only
covers cameras.
"""
import re

_BARE = re.compile(r"[0-9A-Fa-f]{12}")
_SEPARATED = re.compile(r"[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(?:\1[0-9A-Fa-f]{2}){4}")

MAC_FORMAT_HINT = "a MAC address is 6 pairs of hex digits, e.g. 98:BA:5F:8B:10:03 or 98-ba-5f-8b-10-03"


class InvalidMacError(ValueError):
    """Not a MAC in any accepted form. Callers turn this into a 422."""


def normalize_mac(value: object) -> str:
    """Return "AA:BB:CC:DD:EE:FF" for a MAC written with colons, dashes or no
    separators, in any case. One separator style per MAC; anything else raises
    InvalidMacError."""
    if not isinstance(value, str):
        raise InvalidMacError(f"Invalid MAC: {MAC_FORMAT_HINT}.")
    text = value.strip()
    if _BARE.fullmatch(text):
        hexdigits = text
    elif _SEPARATED.fullmatch(text):
        hexdigits = text.replace(":", "").replace("-", "")
    else:
        raise InvalidMacError(f"Invalid MAC: {MAC_FORMAT_HINT}.")
    hexdigits = hexdigits.upper()
    return ":".join(hexdigits[i:i + 2] for i in range(0, 12, 2))


def mac_compact(value: object) -> str:
    """"98BA5F8B1003" - the form camera_key uses."""
    return normalize_mac(value).replace(":", "")


def mac_heartbeat_key(value: object) -> str:
    """"98_BA_5F_8B_10_03" - the /cctv_heartbeats node key (RTDB keys can't
    hold ':' and use underscores like /ap_heartbeats)."""
    return normalize_mac(value).replace(":", "_")
