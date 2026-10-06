"""VIGI IPC Alarm Server payload -> CameraDetection records (Prompt 131 T3).

Pure functions: no I/O, no settings, never raises. Both payload formats the
real InSight S445 sent on 5-6 Oct (tools/harness/fixtures/vigi/,
docs/vigi-integration-design.md Appendix A):

- legacy (Enhanced Alarm Message Service off):
    {"mac": "98-ba-5f-8b-10-03", "device_name": ...,
     "event_list": [{"dateTime": "20261005150501", "event_type": ["MOTION", "PEOPLE"]}]}
  Each entry in an event's event_type list becomes one record; channel 1.
- enhanced (on):
    {"mac": ..., "event_list": [{"camera": "1", "dateTime": "2026-10-05 16:25:31",
      "event_type": "PEOPLE", "extra_text": [{"region_id": [1], "obj_num": 2,
      "obj_rect_info": [{"x": .., "y": .., "height": .., "width": ..}, ...]}]}]}
  This differs from TP-Link's FAQ: event_type is a string, camera a string,
  and extra_text a list of objects.

is_human is True only for PEOPLE; MOTION on its own is never a human. One POST
can carry several events. Unknown fields are ignored. A malformed event is
skipped and counted in stats["skipped"]; the rest of the POST still counts.
"""
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from models.camera_detection import CameraDetection
from utils.mac_utils import InvalidMacError, mac_compact, normalize_mac

LEGACY = "legacy"
ENHANCED = "enhanced"
DEFAULT_TIMEZONE = "UTC+08:00"
_TZ = re.compile(r"^UTC([+-])(\d{2}):(\d{2})$")


class _Malformed(Exception):
    pass


def parse_timezone(tz: Optional[str]) -> timezone:
    """"UTC+08:00" (getTimeZone's format) -> tzinfo. Anything else -> UTC+08:00."""
    m = _TZ.match((tz or "").strip()) or _TZ.match(DEFAULT_TIMEZONE)
    sign = -1 if m.group(1) == "-" else 1
    return timezone(sign * timedelta(hours=int(m.group(2)), minutes=int(m.group(3))))


def _camera_time(raw, fmt: str, tz: timezone) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw.strip(), fmt).replace(tzinfo=tz).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _int_or_none(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _enhanced_extras(extra_text):
    """obj_num, regions, boxes from enhanced extra_text. Several entries: the
    largest obj_num (counting the same people once, not per region)."""
    if not isinstance(extra_text, list):
        return None, None, None
    counts, regions, boxes = [], [], []
    for item in extra_text:
        if not isinstance(item, dict):
            continue
        n = _int_or_none(item.get("obj_num"))
        if n is not None:
            counts.append(n)
        for r in item.get("region_id") or []:
            r = _int_or_none(r)
            if r is not None and r not in regions:
                regions.append(r)
        for rect in item.get("obj_rect_info") or []:
            if isinstance(rect, dict):
                vals = {k: _int_or_none(rect.get(src)) for k, src in
                        (("x", "x"), ("y", "y"), ("w", "width"), ("h", "height"))}
                if all(v is not None for v in vals.values()):
                    boxes.append(vals)
    return (max(counts) if counts else None), (regions or None), (boxes or None)


def _parse_event(ev, *, device_mac: str, source_type: str, source_ip: str,
                 received_at: datetime, tz: timezone) -> List[CameraDetection]:
    if not isinstance(ev, dict):
        raise _Malformed("event is not an object")
    event_type = ev.get("event_type")

    if isinstance(event_type, list):
        fmt_name, channel = LEGACY, 1
        types = [t.strip().upper() for t in event_type if isinstance(t, str) and t.strip()]
        if not types:
            raise _Malformed("legacy event without event types")
        raw_time = ev.get("dateTime")
        cam_utc = _camera_time(raw_time, "%Y%m%d%H%M%S", tz)
        obj_num = regions = boxes = None
    elif isinstance(event_type, str) and event_type.strip():
        fmt_name = ENHANCED
        types = [event_type.strip().upper()]
        camera = ev.get("camera", "1")
        channel = _int_or_none(camera)
        if channel is None or channel < 1:
            raise _Malformed("enhanced event with an unreadable camera channel")
        raw_time = ev.get("dateTime")
        cam_utc = _camera_time(raw_time, "%Y-%m-%d %H:%M:%S", tz)
        obj_num, regions, boxes = _enhanced_extras(ev.get("extra_text"))
    else:
        raise _Malformed("event without an event_type")

    camera_key = f"{source_type}:{mac_compact(device_mac)}:{channel}"
    return [
        CameraDetection(
            camera_key=camera_key,
            source_type=source_type,
            device_mac=device_mac,
            channel=channel,
            event_type=t,
            is_human=(t == "PEOPLE"),
            obj_num=obj_num,
            regions=regions,
            boxes=boxes,
            camera_time_raw=raw_time if isinstance(raw_time, str) else None,
            camera_time_utc=cam_utc,
            received_at=received_at,
            source_ip=source_ip,
            payload_format=fmt_name,
        )
        for t in types
    ]


def parse_ipc_alarm(body, source_ip: str, received_at: datetime, *,
                    camera_timezone: Optional[str] = None,
                    stats: Optional[dict] = None) -> List[CameraDetection]:
    """Turn one Alarm Server body (already JSON-decoded) into detections.

    camera_timezone ("UTC+08:00") only affects camera_time_utc; matching uses
    received_at. stats, if given, gets "events" (records produced) and
    "skipped" (malformed events, or the whole body if it can't be attributed
    to a device) added to it."""
    stats = stats if stats is not None else {}
    stats.setdefault("events", 0)
    stats.setdefault("skipped", 0)
    if not isinstance(body, dict):
        stats["skipped"] += 1
        return []
    try:
        device_mac = normalize_mac(body.get("mac"))
    except InvalidMacError:
        stats["skipped"] += 1
        return []
    events = body.get("event_list")
    if not isinstance(events, list):
        stats["skipped"] += 1
        return []
    tz = parse_timezone(camera_timezone)
    out: List[CameraDetection] = []
    for ev in events:
        try:
            out.extend(_parse_event(ev, device_mac=device_mac, source_type="ipc", source_ip=source_ip,
                                    received_at=received_at, tz=tz))
        except _Malformed:
            stats["skipped"] += 1
        except Exception:   # never raise from here, whatever the payload holds
            stats["skipped"] += 1
    stats["events"] += len(out)
    return out
