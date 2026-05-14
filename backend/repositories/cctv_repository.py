from dataclasses import asdict

from firebase_admin import firestore

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

    def delete(self, building_id: str, floor_id: str, cctv_id: str) -> None:
        self._col(building_id, floor_id).document(cctv_id).delete()


cctv_repository = CCTVRepository()
