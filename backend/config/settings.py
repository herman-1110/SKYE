import ipaddress
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    FIREBASE_KEY_PATH: str
    FIREBASE_RTDB_URL: str        # Realtime Database URL (positions, alerts)
    GEMINI_API_KEY: str
    PORT: int
    DEBUG: bool
    OMADA_ACCESS_TOKEN: str
    OMADA_RAW_DUMP_ENABLED: bool
    OMADA_INGEST_ALLOWED_IPS: tuple   # normalised IPv4 strings; () = no restriction (Prompt 135)
    PATH_LOSS_EXPONENT: float
    TX_POWER_DEFAULT: float
    PATROL_PROXIMITY_RADIUS_M: float
    PATROL_PROXIMITY_EXIT_MARGIN_M: float
    PATROL_NO_PATROL_DWELL_RATIO: float
    MAN_DOWN_MINUTES: int
    MAN_DOWN_MOVEMENT_EPSILON_M: float
    MAN_DOWN_STALE_SECONDS: float
    MAN_DOWN_STALE_MAX_AGE_S: float
    MAN_DOWN_UPGRADE_CONFIRM_S: float
    MAN_DOWN_AP_CHANGE_HOLD_S: float
    MAN_DOWN_RESTART_MATCH_H: float
    MAN_DOWN_MOVE_CONFIRM_FIXES: int
    MAN_DOWN_MOVE_WINDOW_FIXES: int
    MAN_DOWN_ANCHOR_SETTLE_S: float
    AP_SILENT_AFTER_S: float
    AP_ALIVE_GRACE_S: float
    COLLISION_DISTANCE_M: float
    COLLISION_ALERT_SECONDS: int
    COLLISION_MAX_AGE_S: float
    MIN_DWELL_SECONDS: int
    RSSI_NOISE_STD: float
    PROXIMITY_RSSI_FLOOR: float
    POSITION_EXACT_HOLD_SECONDS: float
    POSITION_EMIT_MIN_INTERVAL_S: float
    LLM_PROVIDER: str             # accepts: gemini | openai | ollama | claude
    LLM_MODEL_NAME: str           # passed directly to the active provider
    RAG_SIMILARITY_FLOOR: float
    # VIGI camera (Prompt 131). The two secrets are kept out of repr() so a
    # stray print(settings) can never show them.
    VIGI_ALARM_PATH_SECRET: str = field(repr=False)
    VIGI_CAMERA_PASSWORD: str = field(repr=False)
    VIGI_RAW_DUMP_ENABLED: bool
    VIGI_LIVENESS_INTERVAL_S: float
    VIGI_OPENAPI_INTERVAL_S: float
    VIGI_OPENAPI_START_DELAY_S: float
    VIGI_DISCOVERY_INTERVAL_S: float
    # go2rtc, the live-view relay (Prompt 132)
    GO2RTC_API_URL: str
    GO2RTC_CONFIG_PATH: str
    GO2RTC_WEBRTC_HOST: str
    GO2RTC_FFMPEG_PATH: str


def _go2rtc_path(value: str, default_name: str) -> str:
    """Absolute path of a go2rtc file. Empty means tools/go2rtc/<default_name>
    (gitignored), where tools/go2rtc/start.ps1 looks by default; a relative
    path is taken from backend/, as start.ps1 does."""
    value = value.strip()
    if not value:
        return str(_BACKEND_DIR.parent / "tools" / "go2rtc" / default_name)
    path = Path(value)
    return str(path if path.is_absolute() else (_BACKEND_DIR / path).resolve())


def _ipv4_list(name: str, value: str) -> tuple:
    """A comma-separated list of IPv4 addresses -> a tuple of normalised
    strings; empty or unset -> (). An entry that isn't an IPv4 address stops
    startup with a message naming the setting and the entry, rather than
    being dropped: a dropped entry could silently shut out an AP."""
    out = []
    for part in (value or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(str(ipaddress.IPv4Address(part)))
        except ValueError:
            raise ValueError(f"{name}: {part!r} is not an IPv4 address") from None
    return tuple(out)


def _whole_number(name: str, value: str, minimum: int) -> int:
    """A whole number of at least minimum, written as plain digits. Anything
    else (a fraction, a sign, a word, an empty value, too small) stops startup
    with one sentence naming the setting, rather than falling back to the
    default without a word."""
    text = (value or "").strip()
    if not re.fullmatch(r"[0-9]+", text) or int(text) < minimum:
        raise ValueError(f"{name} must be a whole number of at least {minimum}, not {value!r}.")
    return int(text)


def _positive_seconds(name: str, value: str) -> float:
    """A positive, finite number of seconds. Anything else (0, a negative
    number, inf, nan, a word, an empty value) stops startup with one sentence
    naming the setting, rather than falling back to the default without a
    word."""
    text = (value or "").strip()
    try:
        seconds = float(text)
    except ValueError:
        seconds = math.nan
    if not (math.isfinite(seconds) and seconds > 0):
        raise ValueError(f"{name} must be a positive number of seconds, not {value!r}.")
    return seconds


def _move_fixes(confirm_value: str, window_value: str) -> tuple:
    """MAN_DOWN_MOVE_CONFIRM_FIXES and MAN_DOWN_MOVE_WINDOW_FIXES (Prompt 147b):
    each a whole number of at least 1 (_whole_number), and a move can't need
    more away fixes than the window holds. Anything else stops startup with
    one sentence."""
    confirm = _whole_number("MAN_DOWN_MOVE_CONFIRM_FIXES", confirm_value, 1)
    window = _whole_number("MAN_DOWN_MOVE_WINDOW_FIXES", window_value, 1)
    if confirm > window:
        raise ValueError(f"MAN_DOWN_MOVE_CONFIRM_FIXES ({confirm}) can't be larger than "
                         f"MAN_DOWN_MOVE_WINDOW_FIXES ({window}).")
    return confirm, window


def _load() -> Settings:
    # Checked together, so read before the rest (see the comment at
    # MAN_DOWN_MOVE_CONFIRM_FIXES below).
    move_confirm, move_window = _move_fixes(os.environ.get("MAN_DOWN_MOVE_CONFIRM_FIXES", "3"),
                                            os.environ.get("MAN_DOWN_MOVE_WINDOW_FIXES", "5"))
    return Settings(
        FIREBASE_KEY_PATH=os.environ["FIREBASE_KEY_PATH"],
        FIREBASE_RTDB_URL=os.environ["FIREBASE_RTDB_URL"],
        GEMINI_API_KEY=os.environ["GEMINI_API_KEY"],
        PORT=int(os.environ.get("PORT", "8000")),
        DEBUG=os.environ.get("DEBUG", "false").lower() == "true",
        OMADA_ACCESS_TOKEN=os.environ["OMADA_ACCESS_TOKEN"],
        # Off by default (Prompt 124): the full per-AP raw payload dump in
        # omada_ingest_service.py contains box-drawing characters that throw
        # UnicodeEncodeError under Windows' default cp1252 stdout codepage the
        # moment stdout is piped/redirected (every capture session) — silently
        # 400ing every AP's ingest until PYTHONIOENCODING=utf-8 is set. The
        # permanent null-RSSI counter (Prompt 119) covers the dump's main
        # steady-state use; flip this on only for deep debugging (malformed
        # payload shape, deviceClass/model on an unfamiliar beacon) with
        # PYTHONIOENCODING=utf-8 set first.
        OMADA_RAW_DUMP_ENABLED=os.environ.get("OMADA_RAW_DUMP_ENABLED", "false").lower() == "true",
        # Addresses allowed to post to /telemetry/omada (Prompt 135, SEC-01),
        # checked before the token. Empty: any address, with one startup
        # warning. Set it once the APs have DHCP reservations.
        OMADA_INGEST_ALLOWED_IPS=_ipv4_list("OMADA_INGEST_ALLOWED_IPS",
                                            os.environ.get("OMADA_INGEST_ALLOWED_IPS", "")),
        PATH_LOSS_EXPONENT=float(os.environ.get("PATH_LOSS_EXPONENT", "2.5")),
        TX_POWER_DEFAULT=float(os.environ.get("TX_POWER_DEFAULT", "-59")),
        # Radius (m) within which a guard's smoothed position counts as "at" a
        # patrol-route checkpoint (an AP). Uncalibrated guess — same family as
        # TX_POWER_DEFAULT and PATH_LOSS_EXPONENT, belongs in the RF measurement
        # session once APs are ceiling-mounted, not in a code review.
        PATROL_PROXIMITY_RADIUS_M=float(os.environ.get("PATROL_PROXIMITY_RADIUS_M", "1.0")),
        # Extra distance (m) beyond PATROL_PROXIMITY_RADIUS_M a guard must exceed
        # before an already-entered checkpoint counts as "departed" (Prompt 117).
        # Enter-at-radius / exit-at-radius+margin hysteresis, targeting solve
        # noise flapping in and out of a checkpoint's own zone right at its
        # boundary — confirmed as the cause of 59/69 single-log phantom cycles
        # in the 117a capture. Uncalibrated — same family as
        # PATROL_PROXIMITY_RADIUS_M, to be tuned once APs are ceiling-mounted.
        PATROL_PROXIMITY_EXIT_MARGIN_M=float(os.environ.get("PATROL_PROXIMITY_EXIT_MARGIN_M", "0.5")),
        # Fraction of a patrol window a single checkpoint's dwell must reach
        # before a guard who reached exactly one checkpoint this window
        # (route length >= 2) is flagged no_patrol rather than treated as a
        # legitimate late first arrival cut off by window close (Prompt 125).
        # Never applied when >=2 checkpoints were reached, or on a
        # single-checkpoint route (reaching the only checkpoint IS the
        # patrol there). Uncalibrated — same family as
        # PATROL_PROXIMITY_RADIUS_M, to be tuned once real multi-checkpoint
        # window data exists.
        PATROL_NO_PATROL_DWELL_RATIO=float(os.environ.get("PATROL_NO_PATROL_DWELL_RATIO", "0.5")),
        MAN_DOWN_MINUTES=int(os.environ.get("MAN_DOWN_MINUTES", "5")),
        # Radius (m) within which a person counts as "not moving" for man-down.
        # With RSSI_NOISE_STD=3.0 and PATH_LOSS_EXPONENT=2.5 a stationary beacon's
        # solved position wanders ~1-2 m on its own; a tighter epsilon would let
        # jitter reset the stillness clock and man-down would never fire. Tighten
        # after tx_power calibration reduces jitter.
        MAN_DOWN_MOVEMENT_EPSILON_M=float(os.environ.get("MAN_DOWN_MOVEMENT_EPSILON_M", "2.0")),
        # How long a person's last position may go un-updated before a
        # signal-loss man-down fires (independent of the movement-epsilon
        # check above, which needs a fresh position to evaluate at all).
        # Positions refresh roughly every POSITION_EMIT_MIN_INTERVAL_S (1.8s
        # default, below), so 120s is ~65 missed cycles — long enough
        # to ride out a brief coverage gap, short enough to be actionable.
        # Uncalibrated — same family as MAN_DOWN_MOVEMENT_EPSILON_M and
        # PROXIMITY_RSSI_FLOOR, to be tuned once APs are ceiling-mounted.
        MAN_DOWN_STALE_SECONDS=float(os.environ.get("MAN_DOWN_STALE_SECONDS", "120.0")),
        # Upper bound: a /positions record older than this is a dead record,
        # not an active incident. RTDB positions persist indefinitely after a
        # beacon dies, and the in-memory dedup state is empty on every backend
        # restart — without this cap, every restart re-alerts for every
        # beacon that has ever gone offline.
        MAN_DOWN_STALE_MAX_AGE_S=float(os.environ.get("MAN_DOWN_STALE_MAX_AGE_S", "3600.0")),
        # After an amber possible_man_down (stillness seen by only one or two
        # APs), how long (seconds) exact three-AP fixes must stay within
        # MAN_DOWN_MOVEMENT_EPSILON_M of the first one before the alert is
        # upgraded to a red man_down (Prompt 136, COR-03). One exact fix alone
        # isn't trusted to confirm the person is still where they lay.
        MAN_DOWN_UPGRADE_CONFIRM_S=float(os.environ.get("MAN_DOWN_UPGRADE_CONFIRM_S", "30")),
        # With only one or two APs hearing someone, their position is the
        # strongest AP's own coordinate, and the strongest AP can flip between
        # neighbours every few seconds without the beacon moving. A change of
        # strongest AP counts as movement, and starts a new approximate run,
        # only once no reading has come from the run's own AP for this long
        # (seconds), timed from the first reading away from it, whichever other
        # APs are the strongest meanwhile (Prompt 145, Herman's decision (c),
        # 16 Nov). 120 since 17 Nov: in a replay of 16 Nov, a beacon left on a
        # desk was counted as moving up to once an hour at 30 s, and never at
        # 120 s. Uncalibrated, like MAN_DOWN_MOVEMENT_EPSILON_M.
        MAN_DOWN_AP_CHANGE_HOLD_S=float(os.environ.get("MAN_DOWN_AP_CHANGE_HOLD_S", "120")),
        # After a restart, an unresolved stillness alert for the same person
        # and spot means the episode was already alerted (Prompt 145, D3), but
        # only if it was raised within this many hours: an old one left
        # unresolved at someone's usual spot mustn't hide a new episode there.
        MAN_DOWN_RESTART_MATCH_H=float(os.environ.get("MAN_DOWN_RESTART_MATCH_H", "12")),
        # A move on the exact path: at least MAN_DOWN_MOVE_CONFIRM_FIXES of
        # the last MAN_DOWN_MOVE_WINDOW_FIXES exact fixes land
        # MAN_DOWN_MOVEMENT_EPSILON_M or more from the exact anchor, the latest
        # of them among them (Prompt 147b, Herman's decision, 20 Nov). A beacon
        # lying still gets the odd single fix 2 m or more away, and counting
        # that one fix restarted the stillness clock: on 19 Nov two beacons
        # that lay still for over an hour never reached 60 minutes. Prompt
        # 147's 3 in a row stopped that, but someone walking back and forth
        # through an anchor in the middle of their path seldom lands 3 in a
        # row 2 m from it, and on 20 Nov a walk got a red; 3 of the last 5
        # counts that walk. Exact fixes come about every 2 s. Whole numbers of
        # at least 1, the first no larger than the second; anything else
        # stops startup. 1 of 1 counts a single fix, as before 147, though
        # the anchor still settles (MAN_DOWN_ANCHOR_SETTLE_S).
        MAN_DOWN_MOVE_CONFIRM_FIXES=move_confirm,
        MAN_DOWN_MOVE_WINDOW_FIXES=move_window,
        # How long (seconds) the exact anchor stays at the fix that seeded it
        # (the last fix of a counted move, or a cold start's first) before it
        # settles to the median, x and y separately, of the exact fixes since
        # then, updated with each one until the next move (Prompt 147b).
        # While moves keep being counted it stays frozen, so a walker isn't
        # measured from the middle of their path; once they stop, a stray
        # first fix no longer decides where they lie. Settling restarts
        # neither the stillness clock nor the latch. 60 from the sweep of
        # 20 Nov: 45 to 120 passed every logged case, and 30 settled mid-walk.
        # A positive, finite number; anything else stops startup.
        MAN_DOWN_ANCHOR_SETTLE_S=_positive_seconds("MAN_DOWN_ANCHOR_SETTLE_S",
                                                   os.environ.get("MAN_DOWN_ANCHOR_SETTLE_S", "60")),
        # An AP whose last report is older than this (seconds) is silent
        # (Prompt 136, REL-01). The signal-loss sweep holds a person's alert
        # while none of the APs that last heard them is reporting, and raises
        # one positioning_offline when no placed AP is. Same 10 s as the
        # dashboard's AP online threshold (frontend/hooks/useAPHeartbeats.ts).
        AP_SILENT_AFTER_S=float(os.environ.get("AP_SILENT_AFTER_S", "10")),
        # An AP that has just started reporting again only counts as alive
        # once its current run of reports is this old (seconds): positions
        # take a few seconds to refresh after an outage, and a sweep landing
        # in between would raise signal-loss for everyone who is still there.
        AP_ALIVE_GRACE_S=float(os.environ.get("AP_ALIVE_GRACE_S", "30")),
        COLLISION_DISTANCE_M=float(os.environ.get("COLLISION_DISTANCE_M", "2.0")),
        COLLISION_ALERT_SECONDS=int(os.environ.get("COLLISION_ALERT_SECONDS", "3")),
        # A /positions record older than this (seconds) takes no part in the
        # collision check (Prompt 136, COR-04): a beacon that went dark left
        # its last predicted position behind, and forklifts were "colliding"
        # with it. Positions refresh about every 1.8 s from the APs and every
        # 1 s from the simulators, so 5 s rides out one or two missed updates.
        COLLISION_MAX_AGE_S=float(os.environ.get("COLLISION_MAX_AGE_S", "5")),
        MIN_DWELL_SECONDS=int(os.environ.get("MIN_DWELL_SECONDS", "30")),
        RSSI_NOISE_STD=float(os.environ.get("RSSI_NOISE_STD", "3.0")),
        # Behavioural cutoff for the single-AP proximity fallback: a beacon whose
        # strongest AP is fainter than this is "too far to be a useful anchor" and
        # is treated as gone (no write → record ages out → frontend drops marker).
        # Not a hardware sensitivity limit — the APs receive well below -90 dBm.
        # Tune after ceiling-mount and tx_power calibration.
        PROXIMITY_RSSI_FLOOR=float(os.environ.get("PROXIMITY_RSSI_FLOOR", "-90.0")),
        # How long a recent EXACT solve outranks a fresh approximate (single/dual-AP
        # proximity) estimate for the same beacon. An approximate estimate is
        # strictly worse information than a few-seconds-old exact solve — it's the
        # anchor AP's own coordinate, not a real fix — so within this window the
        # approximate estimate is suppressed rather than emitted (Prompt 111).
        # Uncalibrated — same family as MAN_DOWN_MOVEMENT_EPSILON_M and
        # PROXIMITY_RSSI_FLOOR, to be tuned once the AP-count/flap measurement
        # session runs.
        POSITION_EXACT_HOLD_SECONDS=float(os.environ.get("POSITION_EXACT_HOLD_SECONDS", "10.0")),
        # Minimum seconds between position computations per beacon — the rate
        # limit in omada_ingest_service._flush_ready_beacons (EMIT_MIN_INTERVAL_S
        # there). Was a hard-coded module constant; moved here with the same
        # 1.8 default (Prompt 128) so a calibration capture can lower it for
        # more solves per second of data without a code edit, then set it back.
        POSITION_EMIT_MIN_INTERVAL_S=float(os.environ.get("POSITION_EMIT_MIN_INTERVAL_S", "1.8")),
        LLM_PROVIDER=os.environ.get("LLM_PROVIDER", "gemini"),
        LLM_MODEL_NAME=os.environ["LLM_MODEL_NAME"],
        # Minimum cosine similarity (0-1) for a retrieved feedback example to be
        # surfaced in report context. Uncalibrated — same family as
        # MAN_DOWN_STALE_SECONDS and PROXIMITY_RSSI_FLOOR: a real threshold exists,
        # but tuning it needs a real feedback corpus to test against, which
        # doesn't exist yet. Defaults conservative, not permissive — a weak match
        # injects irrelevant precedent into a safety report with the same
        # authority as a relevant one, which is worse than surfacing nothing.
        RAG_SIMILARITY_FLOOR=float(os.environ.get("RAG_SIMILARITY_FLOOR", "0.5")),
        # Secret path segment the camera's Alarm Server posts to:
        # POST /vigi/alarm/<secret> (Prompt 131). The camera sends no auth
        # header (measured on the real InSight S445, 5 Oct), so the path is
        # the only credential. Unset or shorter than
        # VIGI_ALARM_PATH_SECRET_MIN_LEN: the endpoint answers 404 to
        # everything and startup logs one warning. Never logged; every
        # logged path under /vigi/alarm/ is redacted (utils/log_redaction.py).
        VIGI_ALARM_PATH_SECRET=os.environ.get("VIGI_ALARM_PATH_SECRET", "").strip(),
        # Camera admin password for the read-only OpenAPI health probe
        # (services/vigi_openapi_client.py). Unset: OpenAPI probing is off and
        # the heartbeat's probe reads "no_credentials"; TCP liveness still
        # runs. The camera locks its admin account after repeated failed
        # logins, so the client never retries a rejected password until
        # backend/.env changes. Never logged.
        VIGI_CAMERA_PASSWORD=os.environ.get("VIGI_CAMERA_PASSWORD", ""),
        # Log each raw alarm body with a [VIGI] prefix (never the path).
        # Debugging only, like OMADA_RAW_DUMP_ENABLED.
        VIGI_RAW_DUMP_ENABLED=os.environ.get("VIGI_RAW_DUMP_ENABLED", "false").lower() == "true",
        # Seconds between TCP liveness probes of each camera's RTSP port.
        # Herman's decision 5 (6 Oct): 5 s, so the dashboard's 10 s online
        # threshold (useCCTVHeartbeats.ts) holds without changing the hook.
        VIGI_LIVENESS_INTERVAL_S=float(os.environ.get("VIGI_LIVENESS_INTERVAL_S", "5")),
        # Seconds between OpenAPI health checks per camera (device status,
        # clock, human-detection switch). Slow on purpose: each stok lasts
        # 30 min, so this logs in at most twice an hour per camera.
        VIGI_OPENAPI_INTERVAL_S=float(os.environ.get("VIGI_OPENAPI_INTERVAL_S", "300")),
        # Delay before the first OpenAPI check after startup, so the restarts
        # that --reload causes on every saved .py don't hammer the camera.
        VIGI_OPENAPI_START_DELAY_S=float(os.environ.get("VIGI_OPENAPI_START_DELAY_S", "60")),
        # Seconds between camera discovery rounds (Prompt 131b): one ONVIF
        # WS-Discovery probe per LAN interface (multicast, TTL 1, so it never
        # leaves the local segment), no credentials. One round also runs at
        # startup. 0 turns off both - the harness sets 0 so test servers never
        # probe the real LAN - while the dashboard's "Scan now" (POST
        # /cctvs/discover) still works.
        VIGI_DISCOVERY_INTERVAL_S=float(os.environ.get("VIGI_DISCOVERY_INTERVAL_S", "60")),
        # go2rtc's API, which WebRTC offers for live view are forwarded to
        # (Prompt 132). Loopback: go2rtc's API has no auth of its own, and
        # tools/go2rtc/start.ps1 runs go2rtc on this machine. The backend
        # never starts, stops or restarts go2rtc.
        GO2RTC_API_URL=os.environ.get("GO2RTC_API_URL", "http://127.0.0.1:1984").strip().rstrip("/"),
        # The go2rtc config the backend generates from the camera registry
        # (services/live_view_service.py), rewritten only when it changes;
        # start.ps1 relaunches go2rtc when it does. It holds
        # ${VIGI_CAMERA_PASSWORD}, never the value.
        GO2RTC_CONFIG_PATH=_go2rtc_path(os.environ.get("GO2RTC_CONFIG_PATH", ""), "go2rtc.yaml"),
        # The address go2rtc's WebRTC media listens on (port 8555). Empty means
        # this laptop's LAN address, found from the route to the registered
        # camera. Not 127.0.0.1: Windows won't let a browser's WebRTC sockets
        # (bound to the LAN address) reach loopback - measured in the 132 live
        # check. Windows Firewall's inbound rules decide who else can reach it.
        GO2RTC_WEBRTC_HOST=os.environ.get("GO2RTC_WEBRTC_HOST", "").strip(),
        # ffmpeg, which go2rtc runs per viewing to read the camera and strip
        # its per-frame SEI (copy, no re-encoding): go2rtc 1.9.14's own RTSP
        # reader drops this camera's frames (marker bit on a trailing SEI).
        # Default tools/go2rtc/bin/ffmpeg.exe (gitignored); relative to backend/.
        GO2RTC_FFMPEG_PATH=_go2rtc_path(os.environ.get("GO2RTC_FFMPEG_PATH", ""), "bin/ffmpeg.exe"),
    )


settings = _load()

# Rate limit strings (documentation & reuse in tests)
RATE_LIMIT_AUTH = "5/15minutes"
RATE_LIMIT_GENERAL = "100/minute"
RATE_LIMIT_TELEMETRY = "200/minute"

# A shorter VIGI_ALARM_PATH_SECRET is treated as unset (Prompt 131 T1).
VIGI_ALARM_PATH_SECRET_MIN_LEN = 24
