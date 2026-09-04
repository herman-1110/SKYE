from dataclasses import asdict

from firebase_admin import firestore

from models.ap import AccessPoint


class APRepository:
    def _col(self, building_id: str, floor_id: str):
        return (
            firestore.client()
            .collection("buildings")
            .document(building_id)
            .collection("floors")
            .document(floor_id)
            .collection("access_points")
        )

    def save(self, building_id: str, floor_id: str, ap: AccessPoint) -> AccessPoint:
        self._col(building_id, floor_id).document(ap.id).set(asdict(ap))
        return ap

    def get_all(self, building_id: str, floor_id: str) -> list[AccessPoint]:
        docs = self._col(building_id, floor_id).stream()
        return [AccessPoint(**d.to_dict()) for d in docs]

    def get_by_mac_global(self, mac: str) -> list[AccessPoint]:
        """Return all AP documents across ALL buildings and floors that match this MAC (case-insensitive)."""
        docs = (
            firestore.client()
            .collection_group("access_points")
            .where("mac", "==", mac.upper())
            .stream()
        )
        return [AccessPoint(**d.to_dict()) for d in docs]

    def update_coordinates(self, building_id: str, floor_id: str, ap_id: str, x_m: float, y_m: float) -> None:
        self._col(building_id, floor_id).document(ap_id).update({
            "x_m": round(x_m, 4),
            "y_m": round(y_m, 4),
        })

    def update_position(
        self, building_id: str, floor_id: str, ap_id: str,
        x_pct: float, y_pct: float, x_m: float, y_m: float,
    ) -> None:
        """User dragged the marker on the map — x_pct/y_pct are the new image
        fraction, x_m/y_m the frontend's re-derivation from the floor's current
        scale (same formula as placement). Both stored together so they never
        drift apart the way a scale-only recompute could leave them."""
        self._col(building_id, floor_id).document(ap_id).update({
            "x_pct": x_pct,
            "y_pct": y_pct,
            "x_m": round(x_m, 4),
            "y_m": round(y_m, 4),
        })

    def delete(self, building_id: str, floor_id: str, ap_id: str) -> str | None:
        """Delete AP document from Firestore. Returns the AP's MAC address, or None if not found."""
        doc_ref = self._col(building_id, floor_id).document(ap_id)
        doc = doc_ref.get()
        if not doc.exists:
            return None
        mac = (doc.to_dict() or {}).get("mac")
        doc_ref.delete()
        return mac


ap_repository = APRepository()
