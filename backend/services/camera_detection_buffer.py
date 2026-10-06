"""Recent camera detections, in memory, per camera_key (Prompt 131 T7).

The last 15 minutes of normalized alarm events for each camera, for the
dashboard's camera panel now and for Ghost Patrol's matching window in 133
(design §4). Nothing here is persisted: a restart empties it, which is why
process_started_at is reported with every read - a window that overlaps a
restart can't claim "no human seen".

Own lock; never touches positioning_service.pipeline_lock. Per-process state:
under more than one worker each would hold its own buffer (same caveat as
patrol_tracker_service).
"""
import threading
import time
from collections import deque
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from models.camera_detection import CameraDetection
from utils.timestamp_utils import utcnow_iso

WINDOW_S = 15 * 60
# A busy camera sent ~20 pushes/min on 5 Oct, some with two events each; 4000
# entries covers 15 minutes at over 4 events/s per camera.
MAX_ENTRIES_PER_CAMERA = 4000


class DetectionBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_camera: Dict[str, Deque[Tuple[float, dict]]] = {}
        self.process_started_at: str = utcnow_iso()

    def mark_process_start(self) -> None:
        self.process_started_at = utcnow_iso()

    @staticmethod
    def _prune(entries: Deque[Tuple[float, dict]], now: float) -> None:
        cutoff = now - WINDOW_S
        while entries and entries[0][0] < cutoff:
            entries.popleft()

    def add_many(self, detections: Iterable[CameraDetection]) -> int:
        added = 0
        now = time.time()
        with self._lock:
            for d in detections:
                entries = self._by_camera.get(d.camera_key)
                if entries is None:
                    entries = deque(maxlen=MAX_ENTRIES_PER_CAMERA)
                    self._by_camera[d.camera_key] = entries
                entries.append((d.received_at.timestamp(), {
                    "received_at": d.received_at.isoformat(),
                    "event_type": d.event_type,
                    "is_human": d.is_human,
                    "obj_num": d.obj_num,
                    "payload_format": d.payload_format,
                }))
                self._prune(entries, now)
                added += 1
        return added

    def recent(self, camera_key: Optional[str]) -> List[dict]:
        """The last 15 minutes for one camera, newest first."""
        if not camera_key:
            return []
        now = time.time()
        with self._lock:
            entries = self._by_camera.get(camera_key)
            if not entries:
                return []
            self._prune(entries, now)
            return [dict(item) for _, item in reversed(entries)]

    def drop(self, camera_key: Optional[str]) -> None:
        if not camera_key:
            return
        with self._lock:
            self._by_camera.pop(camera_key, None)


detection_buffer = DetectionBuffer()
