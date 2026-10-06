from dataclasses import asdict
from typing import Optional

from firebase_admin import firestore
from firebase_admin import db as rtdb

from models.cctv import CCTV
from utils.mac_utils import InvalidMacError, mac_heartbeat_key, normalize_mac


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
        return [CCTV.from_dict(d.to_dict()) for d in docs]

    def get_by_id(self, building_id: str, floor_id: str, cctv_id: str) -> Optional[CCTV]:
        doc = self._col(building_id, floor_id).document(cctv_id).get()
        if not doc.exists:
            return None
        return CCTV.from_dict(doc.to_dict())

    def get_all_global(self) -> list[CCTV]:
        """Every camera on every floor. Unfiltered on purpose: a filtered
        collection-group query needs a collection-group index, and there are
        only ever a handful of cameras."""
        docs = firestore.client().collection_group("cctvs").stream()
        return [CCTV.from_dict(d.to_dict()) for d in docs]

    def update_fields(self, building_id: str, floor_id: str, cctv_id: str, values: dict) -> None:
        self._col(building_id, floor_id).document(cctv_id).update(values)

    def update_position(self, building_id: str, floor_id: str, cctv_id: str, x_pct: float, y_pct: float) -> None:
        self._col(building_id, floor_id).document(cctv_id).update({
            "x_pct": x_pct,
            "y_pct": y_pct,
        })

    def delete(self, building_id: str, floor_id: str, cctv_id: str) -> None:
        self._col(building_id, floor_id).document(cctv_id).delete()

    # ── /cctv_heartbeats (Prompt 131 T8) ─────────────────────────────────────
    # The one writer for heartbeat nodes: TCP liveness, alarm ingest and the
    # OpenAPI check all go through update_heartbeat(). It's a partial update,
    # so no writer wipes the fields another one set.

    def update_heartbeat(self, mac: str, values: dict, remove=()) -> None:
        """Set the given fields (None values skipped) and delete the fields in
        `remove` (RTDB deletes a key updated to None); nothing else changes."""
        mac_norm = normalize_mac(mac)
        payload = {k: v for k, v in values.items() if v is not None}
        for key in remove:
            payload[key] = None
        payload["mac"] = mac_norm
        rtdb.reference(f"/cctv_heartbeats/{mac_heartbeat_key(mac_norm)}").update(payload)

    def get_all_heartbeats(self) -> dict:
        """Every /cctv_heartbeats node, keyed by node key (for discovery's pruning)."""
        nodes = rtdb.reference("/cctv_heartbeats").get()
        return nodes if isinstance(nodes, dict) else {}

    def delete_cctv_heartbeat(self, mac: str) -> None:
        try:
            key = mac_heartbeat_key(mac)
        except InvalidMacError:
            key = mac.replace(":", "_")   # a pre-131 record with an odd MAC
        rtdb.reference(f"/cctv_heartbeats/{key}").delete()


cctv_repository = CCTVRepository()
