import threading
import uuid
from typing import Any, Dict, List, Optional

from models.ap import AccessPoint
from models.floor import FloorRecord
from repositories.ap_repository import ap_repository
from repositories.building_repository import building_repository
from repositories.cctv_repository import cctv_repository
from repositories.floor_repository import floor_repository
from repositories.position_repository import position_repository
from repositories.zone_repository import zone_repository
from services.positioning_service import positioning_service
from firebase_admin import storage
from utils.timestamp_utils import utcnow_iso


class FloorError(Exception):
    """A floor or AP request that can't be done as asked: the route answers
    with this status and message. conflicts rides along when an activation
    is refused because of shared APs (Prompt 142, D1.3)."""

    def __init__(self, status: int, message: str, conflicts: Optional[List[dict]] = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.conflicts = conflicts


# Several floors can be active at once, but an AP (by MAC) on at most one of
# them (Prompt 142, D1.2). Activation and AP placement each check, then write,
# under this lock, so two requests can't put one AP on two active floors
# between them. There is one backend process, and the checks are queries,
# which a Firestore transaction couldn't hold.
_placement_lock = threading.Lock()


def _invalidate_ap_cache() -> None:
    # local import, as for the simulators and cctv_service below
    from services.omada_ingest_service import omada_ingest_service
    omada_ingest_service.invalidate_ap_cache()


class FloorService:

    def get_all(self, building_id: str) -> List[FloorRecord]:
        return floor_repository.get_all(building_id)

    def create(
        self,
        building_id: str,
        name: Optional[str],
        floor_number: int,
        url: str,
        storage_path: str,
        image_width_px: Optional[int] = None,
        image_height_px: Optional[int] = None,
    ) -> FloorRecord:
        if not name or not name.strip():
            existing = floor_repository.get_all(building_id)
            name = f"Level {len(existing) + 1}"
        floor = FloorRecord(
            id=str(uuid.uuid4()),
            building_id=building_id,
            name=name,
            floor_number=floor_number,
            url=url,
            storage_path=storage_path,
            is_active=False,
            uploaded_at=utcnow_iso(),
            image_width_px=image_width_px,
            image_height_px=image_height_px,
        )
        return floor_repository.save(floor)

    def update_scale(
        self, building_id: str, floor_id: str, scale: float, calibration: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Set the floor's px/m (Prompt 142, D3).

        calibration, when sent, is the two points (image fractions) and the
        distance they were measured with: the floor keeps it for the next
        Recalibrate. A scale sent without it clears the stored one, which no
        longer describes the scale. FloorError 422 with one sentence for a
        point off the image, A equal to B, a distance outside (0, 10000] m, or
        a calibration missing a part.

        Zones are stored in metres, so each one's bounds are multiplied by
        old ÷ new px/m to keep it where it's drawn on the image. A first
        calibration (no old scale) leaves zones alone. APs are re-derived from
        their image fractions, as before."""
        if scale <= 0:
            raise ValueError("scale_pixels_per_meter must be positive")
        stored = self._checked_calibration(calibration) if calibration is not None else None
        floor = floor_repository.get_by_id(building_id, floor_id)
        old = floor.scale_pixels_per_meter if floor else None
        zone_bounds: Dict[str, Dict[str, float]] = {}
        if old and old > 0 and old != scale:
            ratio = old / scale
            for zone in zone_repository.get_all(building_id, floor_id):
                zone_bounds[zone.id] = {k: round(getattr(zone, k) * ratio, 4)
                                        for k in ("x_min", "x_max", "y_min", "y_max")}
        floor_repository.update_scale(building_id, floor_id, scale, stored, zone_bounds)
        positioning_service.invalidate_scale_cache()
        self._recalculate_ap_coordinates(building_id, floor_id, scale)
        if zone_bounds:
            print(f"[CALIBRATION] Rescaled {len(zone_bounds)} zone(s) by {old} / {scale} px/m to keep them in place")
        # Every AP's metres just changed: the ingest mustn't keep using the
        # old ones until its cache expires (Prompt 142).
        _invalidate_ap_cache()

    @staticmethod
    def _checked_calibration(calibration: Dict[str, Any]) -> Dict[str, Any]:
        """The calibration as stored: {a: {x_pct, y_pct}, b: {x_pct, y_pct},
        distance_m, calibrated_at}. FloorError 422 with one sentence otherwise."""
        a, b = calibration.get("a") or {}, calibration.get("b") or {}
        points = [a.get("x_pct"), a.get("y_pct"), b.get("x_pct"), b.get("y_pct")]
        distance = calibration.get("distance_m")
        if any(v is None for v in points) or distance is None:
            raise FloorError(422, "Send both calibration points and the distance between them, or none of them.")
        if not all(0.0 <= v <= 1.0 for v in points):
            raise FloorError(422, "Each calibration point must be on the floor plan (fractions from 0 to 1).")
        if points[:2] == points[2:]:
            raise FloorError(422, "The two calibration points must be different.")
        if not 0.0 < distance <= 10_000.0:
            raise FloorError(422, "The distance must be more than 0 m and at most 10,000 m.")
        return {
            "a": {"x_pct": points[0], "y_pct": points[1]},
            "b": {"x_pct": points[2], "y_pct": points[3]},
            "distance_m": distance,
            "calibrated_at": utcnow_iso(),
        }

    def derive_ap_metres(self, building_id: str, floor_id: str, x_pct: float, y_pct: float) -> tuple[float, float]:
        """Re-derive real-world metre coordinates from x_pct/y_pct — same
        arithmetic _recalculate_ap_coordinates() applies when re-deriving every
        AP on a floor after a scale change, used here instead for one AP at
        create/reposition time. Raises ValueError if the floor isn't
        calibrated; callers turn that into a 409 (placement/reposition on an
        uncalibrated floor would otherwise store zeroed coordinates)."""
        floor = floor_repository.get_by_id(building_id, floor_id)
        if not floor or not floor.scale_pixels_per_meter or not floor.image_width_px or not floor.image_height_px:
            raise ValueError(
                "Floor is not calibrated — set the scale before placing APs. "
                "Placing now would store zeroed coordinates and break positioning."
            )
        x_m = x_pct * floor.image_width_px / floor.scale_pixels_per_meter
        y_m = y_pct * floor.image_height_px / floor.scale_pixels_per_meter
        return x_m, y_m

    def _recalculate_ap_coordinates(self, building_id: str, floor_id: str, scale: float) -> None:
        floor = floor_repository.get_by_id(building_id, floor_id)
        if not floor or not floor.image_width_px or not floor.image_height_px:
            print(f"[CALIBRATION] Floor {floor_id} missing image dimensions — AP coordinates not recalculated")
            return
        aps = ap_repository.get_all(building_id, floor_id)
        for ap in aps:
            new_x_m = ap.x_pct * floor.image_width_px  / scale
            new_y_m = ap.y_pct * floor.image_height_px / scale
            ap_repository.update_coordinates(building_id, floor_id, ap.id, new_x_m, new_y_m)
        print(f"[CALIBRATION] Recalculated coordinates for {len(aps)} AP(s) on floor '{floor.name}' → {scale} px/m")

    def set_active(self, building_id: str, floor_id: str) -> None:
        """Activate a floor, leaving every other floor as it is: several can
        be active at once (Prompt 142, D1.1). Refused with a 409 that lists
        each other active floor holding one of this floor's APs (D1.3). A
        floor with no APs can always be activated, calibrated or not."""
        with _placement_lock:
            floor = floor_repository.get_by_id(building_id, floor_id)
            if floor is None:
                raise FloorError(404, "Floor not found.")
            if not floor.is_active:
                conflicts = self._activation_conflicts(floor)
                if conflicts:
                    raise FloorError(409, self._activation_message(floor, conflicts), conflicts)
                floor_repository.set_active(building_id, floor_id)
        positioning_service.invalidate_scale_cache()
        _invalidate_ap_cache()

    def _activation_conflicts(self, floor: FloorRecord) -> List[dict]:
        """Every other active floor that holds one of this floor's APs (by
        MAC), with the shared APs as they're named there."""
        macs = {ap.mac.upper() for ap in ap_repository.get_all(floor.building_id, floor.id)}
        if not macs:
            return []
        conflicts = []
        building_names: Dict[str, str] = {}
        for other in floor_repository.get_all_active():
            if other.id == floor.id:
                continue
            shared = [ap for ap in ap_repository.get_all(other.building_id, other.id) if ap.mac.upper() in macs]
            if not shared:
                continue
            if other.building_id not in building_names:
                building = building_repository.get_by_id(other.building_id) or {}
                building_names[other.building_id] = building.get("name") or other.building_id
            conflicts.append({
                "floor_id": other.id,
                "floor_name": other.name,
                "building_id": other.building_id,
                "building_name": building_names[other.building_id],
                "aps": [{"name": ap.name, "mac": ap.mac} for ap in sorted(shared, key=lambda a: a.mac)],
            })
        return sorted(conflicts, key=lambda c: (c["building_name"], c["floor_name"]))

    @staticmethod
    def _activation_message(floor: FloorRecord, conflicts: List[dict]) -> str:
        if len(conflicts) == 1:
            c = conflicts[0]
            n = len(c["aps"])
            return (f"Can't activate {floor.name}: it shares {n} AP{'' if n == 1 else 's'} with "
                    f"{c['floor_name']} in {c['building_name']}, which is active.")
        return f"Can't activate {floor.name}: it shares APs with {len(conflicts)} active floors."

    def deactivate(self, building_id: str, floor_id: str) -> None:
        floor_repository.deactivate(building_id, floor_id)
        positioning_service.invalidate_scale_cache()
        _invalidate_ap_cache()

    def rename(self, building_id: str, floor_id: str, name: str) -> None:
        floor_repository.update(building_id, floor_id, {"name": name})

    def delete(self, building_id: str, floor_id: str) -> None:
        floor = floor_repository.get_by_id(building_id, floor_id)
        if not floor:
            return

        # 1. Delete all zones in this floor
        zones = zone_repository.get_all(building_id, floor_id)
        for zone in zones:
            zone_repository.delete(building_id, floor_id, zone.id)

        # 2. Delete all APs — Firestore docs, then each MAC's RTDB heartbeat,
        #    unless another floor still holds that AP (Prompt 142, D1.8)
        aps = ap_repository.get_all(building_id, floor_id)
        for ap in aps:
            ap_repository.delete(building_id, floor_id, ap.id)
        for mac in sorted({ap.mac for ap in aps if ap.mac}):
            if not ap_repository.get_by_mac_global(mac):
                position_repository.delete_ap_heartbeat(mac)
        if aps:
            _invalidate_ap_cache()

        # 3. Delete all CCTVs — Firestore docs + RTDB heartbeats
        cctvs = cctv_repository.get_all(building_id, floor_id)
        for cctv in cctvs:
            cctv_repository.delete(building_id, floor_id, cctv.id)
            if cctv.device_mac or cctv.mac:
                cctv_repository.delete_cctv_heartbeat(cctv.device_mac or cctv.mac)
        if cctvs:
            from services.cctv_service import cctv_service
            cctv_service.invalidate()

        # 4. Delete floorplan image from Firebase Storage
        if floor.storage_path:
            try:
                bucket = storage.bucket("skye-3fa05.firebasestorage.app")
                blob = bucket.blob(floor.storage_path)
                if blob.exists():
                    blob.delete()
            except Exception as e:
                print(f"Failed to delete storage file {floor.storage_path}: {e}")

        # 5. Delete floor document
        floor_repository.delete(building_id, floor_id)

    def create_ap(
        self, building_id: str, floor_id: str, name: str, mac: str, x_pct: float, y_pct: float,
    ) -> AccessPoint:
        """Place an AP (mac upper-case, colon form). One placement per floor.
        Other floors may hold the same MAC, a backup map for example, but an
        active floor may not if another active floor already does (Prompt
        142, D1.4). x_m/y_m come from the floor's scale (derive_ap_metres)."""
        with _placement_lock:
            matches = ap_repository.get_by_mac_global(mac)
            if any(m.floor_id == floor_id for m in matches):
                raise FloorError(409, f"AP with MAC {mac} already exists on this floor")
            floor = floor_repository.get_by_id(building_id, floor_id)
            if floor is not None and floor.is_active:
                for m in matches:
                    other = floor_repository.get_by_id(m.building_id, m.floor_id)
                    if other is not None and other.is_active:
                        building = building_repository.get_by_id(other.building_id) or {}
                        raise FloorError(409, (
                            f"AP {mac} is already on {other.name} in {building.get('name') or other.building_id}, "
                            f"which is active: deactivate that floor first, or place this AP on an inactive floor."))
            try:
                x_m, y_m = self.derive_ap_metres(building_id, floor_id, x_pct, y_pct)
            except ValueError as e:
                # 409, not 400: the request itself is well-formed — the floor is
                # just in the wrong state (uncalibrated) to place an AP on right now.
                raise FloorError(409, str(e))
            ap = AccessPoint(
                id=str(uuid.uuid4()),
                floor_id=floor_id,
                building_id=building_id,
                name=name,
                mac=mac,
                x_pct=x_pct,
                y_pct=y_pct,
                created_at=utcnow_iso(),
                x_m=x_m,
                y_m=y_m,
            )
            ap_repository.save(building_id, floor_id, ap)
        _invalidate_ap_cache()
        return ap

    def move_ap(self, building_id: str, floor_id: str, ap_id: str, x_pct: float, y_pct: float) -> None:
        """The marker was dragged. x_m/y_m are re-derived from the floor's
        current scale, as at placement. Raises ValueError on an uncalibrated
        floor (the route answers 409)."""
        x_m, y_m = self.derive_ap_metres(building_id, floor_id, x_pct, y_pct)
        ap_repository.update_position(building_id, floor_id, ap_id, x_pct, y_pct, x_m, y_m)
        _invalidate_ap_cache()

    def delete_ap(self, building_id: str, floor_id: str, ap_id: str) -> None:
        # Take the AP out of the patrol route first, with an update that
        # touches only patrol_route (Prompt 135, COR-08). This used to run
        # last, through update_patrol_config() with four of its five
        # arguments, so deleting an AP that was on a route raised TypeError -
        # a 500 - after the AP itself was already gone.
        floor = floor_repository.get_by_id(building_id, floor_id)
        if floor and ap_id in floor.patrol_route:
            floor_repository.update_patrol_route(
                building_id, floor_id, [pid for pid in floor.patrol_route if pid != ap_id])

        mac = ap_repository.delete(building_id, floor_id, ap_id)
        if mac:
            # Another floor may hold the same AP (Prompt 142): its heartbeat
            # stays until the last placement goes (D1.8). Checked after the
            # delete, so this placement no longer counts.
            if not ap_repository.get_by_mac_global(mac):
                position_repository.delete_ap_heartbeat(mac)
            from services.simulation_patrol import remove_ap as patrol_remove_ap
            from services.simulation_events import remove_ap as events_remove_ap
            # By placement id, not MAC: deleting a backup copy mustn't take
            # the AP out of a simulation running on the active floor (D1.9).
            patrol_remove_ap(ap_id)
            events_remove_ap(ap_id)
            _invalidate_ap_cache()

        # Cameras that covered this checkpoint now cover nothing (Prompt 131 T2).
        from services.cctv_service import cctv_service
        cctv_service.unlink_ap(building_id, floor_id, ap_id)


floor_service = FloorService()
