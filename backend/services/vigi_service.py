import time

from firebase_admin import db


class VigiService:
    def write_cctv_heartbeat(self, mac: str, device_name: str = "Unknown CCTV") -> None:
        mac_key = mac.replace(":", "_")
        db.reference(f"/cctv_heartbeats/{mac_key}").set({
            "last_seen": int(time.time()),
            "mac": mac.upper(),
            "device_name": device_name,
        })


vigi_service = VigiService()
