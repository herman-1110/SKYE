from dataclasses import asdict

from firebase_admin import firestore
from firebase_admin import db as rtdb

from models.cctv import CCTV


class CCTVRepository:
    def _col(self, building_id: str, floor_id: str):
        return (
            firestore.client()
            .collection("buildings")
            .document(building_id)
            .collection("floors")
            .document(floor_id)
            .collection("cctvs")
        )

    def save(self, building_id: str, floor_id: str, cctv: CCTV) -> CCTV:
        self._col(building_id, floor_id).document(cctv.id).set(asdict(cctv))
        return cctv

    def get_all(self, building_id: str, floor_id: str) -> list[CCTV]:
        docs = self._col(building_id, floor_id).stream()
        return [CCTV(**d.to_dict()) for d in docs]

    def update_position(self, building_id: str, floor_id: str, cctv_id: str, x_pct: float, y_pct: float) -> None:
        self._col(building_id, floor_id).document(cctv_id).update({
            "x_pct": x_pct,
            "y_pct": y_pct,
        })

    def delete(self, building_id: str, floor_id: str, cctv_id: str) -> None:
        self._col(building_id, floor_id).document(cctv_id).delete()

    def delete_cctv_heartbeat(self, mac: str) -> None:
        key = mac.replace(":", "_")
        rtdb.reference(f"/cctv_heartbeats/{key}").delete()


cctv_repository = CCTVRepository()
