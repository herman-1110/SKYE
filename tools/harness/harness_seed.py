"""Seed the in-memory fakes with the p128 test world.

Every document is shaped exactly as the backend writes it (dataclass
__dict__ / asdict of the real models), so repository reads (AccessPoint(**d),
Beacon(**d), FloorRecord via _to_record, UserRecord(**d), PositionRecord(**v))
behave as they would against real Firebase. Written through the fake
firebase_admin API itself (same normalization as app writes).
"""
import datetime as _dt
import os

import harness_common as C


def _iso(offset_s: float = 0.0) -> str:
    return (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=offset_s)).isoformat()


def seed(store) -> dict:
    from firebase_admin import db, firestore  # the fakes (install_fakes ran first)

    fs = firestore.client()
    now = _iso()
    summary = {}

    store.op_logging = False
    try:
        # buildings/{id}  — BuildingRecord.__dict__
        fs.collection("buildings").document(C.BUILDING_ID).set({
            "id": C.BUILDING_ID,
            "name": "T128 Test Building",
            "description": "p128 harness (in-memory fake)",
            "user_id": "harness-owner",
            "created_at": now,
        })

        # buildings/{id}/floors/{id} — FloorRecord.__dict__ (incl. the
        # patrol_proximity_radius_m dataclass default that real saves carry).
        # patrol_enabled False + empty route => patrol tracker returns early.
        fs.collection("buildings").document(C.BUILDING_ID).collection("floors").document(C.FLOOR_ID).set({
            "id": C.FLOOR_ID,
            "building_id": C.BUILDING_ID,
            "name": "T128 Level",
            "floor_number": 1,
            "url": "harness://floor-t128.png",
            "storage_path": f"floors/{C.BUILDING_ID}/{C.FLOOR_ID}.png",
            "is_active": True,
            "uploaded_at": now,
            "scale_pixels_per_meter": C.SCALE_PX_PER_M,
            "image_width_px": C.IMAGE_W_PX,
            "image_height_px": C.IMAGE_H_PX,
            "patrol_enabled": False,
            "patrol_route": [],
            "patrol_interval_minutes": 10,
            "patrol_proximity_radius_m": 0.0,
        })

        # .../access_points/{id} — asdict(AccessPoint); x_pct/y_pct consistent
        # with floor_service.derive_ap_metres (x_m = x_pct * W / scale).
        apcol = (fs.collection("buildings").document(C.BUILDING_ID)
                 .collection("floors").document(C.FLOOR_ID).collection("access_points"))
        for ap in C.APS:
            apcol.document(ap["id"]).set({
                "id": ap["id"],
                "floor_id": C.FLOOR_ID,
                "building_id": C.BUILDING_ID,
                "name": ap["doc_name"],
                "mac": ap["mac"],
                "x_pct": ap["x_m"] * C.SCALE_PX_PER_M / C.IMAGE_W_PX,
                "y_pct": ap["y_m"] * C.SCALE_PX_PER_M / C.IMAGE_H_PX,
                "created_at": now,
                "x_m": round(ap["x_m"], 4),
                "y_m": round(ap["y_m"], 4),
            })
        summary["aps"] = [(a["mac"], a["x_m"], a["y_m"]) for a in C.APS]

        # beacons/{uuid:major:minor} — asdict(Beacon) as beacon_service.create writes it
        for minor, b in C.BEACONS.items():
            key = C.beacon_key(minor)
            fs.collection("beacons").document(key).set({
                "id": key,
                "uuid": C.BEACON_UUID_WIRE.lower(),
                "major": C.BEACON_MAJOR,
                "minor": minor,
                "person_id": b["person_id"],
                "person_type": b["person_type"],
                "label": b["label"],
                "created_at": now,
                "updated_at": now,
                "building_id": None,
                "tx_power": b["tx_power"],
            })
        summary["beacons"] = {C.beacon_key(m): b["person_id"] for m, b in C.BEACONS.items()}

        # users/{uid} — one owner, so ensure_owner_exists() runs its
        # order_by(created_at DESC) path over real data and returns None.
        fs.collection("users").document("harness-owner").set({
            "uid": "harness-owner",
            "email": "harness-owner@example.invalid",
            "display_name": "Harness Owner",
            "role": "owner",
            "status": "approved",
            "person_id": "",
            "created_at": now,
            "email_verified": True,
        })

        # settings/safety is intentionally NOT seeded: the app's own
        # safety_settings_repository.seed_defaults() creates it at startup.

        # RTDB: a stale worker position so the 60 s man-down sweeper has work
        # (fires one signal_loss alert on its first tick).
        if os.environ.get("HARNESS_SEED_STALE", "1") != "0":
            db.reference(f"/positions/{C.STALE_PERSON_ID}").set({
                "beacon_mac": C.STALE_PERSON_ID,
                "person_id": C.STALE_PERSON_ID,
                "person_type": "worker",
                "x": 17.0,
                "y": 13.0,
                "zone": "unknown",
                "timestamp": _iso(-C.STALE_AGE_S),
                "predicted_x": 17.0,
                "predicted_y": 13.0,
                "pixel_x": 850.0,
                "pixel_y": 650.0,
                "is_stationary": False,
                "floor_id": C.FLOOR_ID,
                "building_id": C.BUILDING_ID,
                "label": "T128 Stale",
                "radius_m": None,
                "is_approximate": False,
                "anchor_ap_mac": None,
            })
            summary["stale_position_seeded"] = C.STALE_PERSON_ID
    finally:
        store.op_logging = True
    return summary
