from dataclasses import asdict, dataclass, fields
from typing import Optional

from utils.mac_utils import InvalidMacError, normalize_mac

DEFAULT_CAMERA_TIMEZONE = "UTC+08:00"


@dataclass
class CCTV:
    id: str
    floor_id: str
    building_id: str
    name: str
    x_pct: float    # 0.0–1.0 fraction of image width
    y_pct: float    # 0.0–1.0 fraction of image height
    created_at: str
    mac: Optional[str] = None
    # Camera identity and checkpoint link (Prompt 131, docs/vigi-integration-design.md §1).
    # Defaults are what a record written before 131 means.
    source_type: str = "ipc"                 # "ipc" (camera posts itself) | "nvr" (later)
    device_mac: Optional[str] = None         # reporting device, "AA:BB:CC:DD:EE:FF"; == mac for ipc
    channel: int = 1
    ip: Optional[str] = None                 # alarms are only accepted from this address
    checkpoint_ap_id: Optional[str] = None   # an AP on the same floor, or None
    timezone: Optional[str] = None           # e.g. "UTC+08:00", read from the camera at registration

    @property
    def camera_key(self) -> Optional[str]:
        """"ipc:98BA5F8B1003:1" - (source_type, device MAC, channel). None
        while no MAC is set, since a MAC-less camera can't report anything."""
        if not self.device_mac:
            return None
        return f"{self.source_type}:{self.device_mac.replace(':', '')}:{self.channel}"

    @classmethod
    def from_dict(cls, data: dict) -> "CCTV":
        """Read a Firestore doc in either shape. Unknown keys are ignored, and a
        pre-131 record (mac only) gets device_mac derived from mac."""
        known = {f.name for f in fields(cls)}
        cctv = cls(**{k: v for k, v in (data or {}).items() if k in known})
        if not cctv.source_type:
            cctv.source_type = "ipc"
        try:
            cctv.channel = int(cctv.channel or 1)
        except (TypeError, ValueError):
            cctv.channel = 1
        for attr in ("mac", "device_mac"):
            value = getattr(cctv, attr)
            if value:
                try:
                    setattr(cctv, attr, normalize_mac(value))
                except InvalidMacError:
                    pass
        if not cctv.device_mac and cctv.mac and cctv.source_type == "ipc":
            cctv.device_mac = cctv.mac
        return cctv

    def to_dict(self) -> dict:
        """API shape: the stored fields plus the derived camera_key."""
        out = asdict(self)
        out["camera_key"] = self.camera_key
        return out
