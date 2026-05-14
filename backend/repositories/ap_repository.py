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

    def delete(self, building_id: str, floor_id: str, ap_id: str) -> None:
        self._col(building_id, floor_id).document(ap_id).delete()


ap_repository = APRepository()
