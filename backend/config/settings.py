import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    FIREBASE_KEY_PATH: str
    FIREBASE_RTDB_URL: str        # Realtime Database URL (positions, alerts)
    GEMINI_API_KEY: str
    PORT: int
    DEBUG: bool
    OMADA_ACCESS_TOKEN: str
    PATH_LOSS_EXPONENT: float
    TX_POWER_DEFAULT: float
    PATROL_PROXIMITY_RADIUS_M: float
    MAN_DOWN_MINUTES: int
    MAN_DOWN_MOVEMENT_EPSILON_M: float
    MAN_DOWN_STALE_SECONDS: float
    MAN_DOWN_STALE_MAX_AGE_S: float
    COLLISION_DISTANCE_M: float
    COLLISION_ALERT_SECONDS: int
    MIN_DWELL_SECONDS: int
    RSSI_NOISE_STD: float
    PROXIMITY_RSSI_FLOOR: float
    LLM_PROVIDER: str             # accepts: gemini | openai | ollama | claude
    LLM_MODEL_NAME: str           # passed directly to the active provider
    RAG_SIMILARITY_FLOOR: float


def _load() -> Settings:
    return Settings(
        FIREBASE_KEY_PATH=os.environ["FIREBASE_KEY_PATH"],
        FIREBASE_RTDB_URL=os.environ["FIREBASE_RTDB_URL"],
        GEMINI_API_KEY=os.environ["GEMINI_API_KEY"],
        PORT=int(os.environ.get("PORT", "8000")),
        DEBUG=os.environ.get("DEBUG", "false").lower() == "true",
        OMADA_ACCESS_TOKEN=os.environ["OMADA_ACCESS_TOKEN"],
        PATH_LOSS_EXPONENT=float(os.environ.get("PATH_LOSS_EXPONENT", "2.5")),
        TX_POWER_DEFAULT=float(os.environ.get("TX_POWER_DEFAULT", "-59")),
        # Radius (m) within which a guard's smoothed position counts as "at" a
        # patrol-route checkpoint (an AP). Uncalibrated guess — same family as
        # TX_POWER_DEFAULT and PATH_LOSS_EXPONENT, belongs in the RF measurement
        # session once APs are ceiling-mounted, not in a code review.
        PATROL_PROXIMITY_RADIUS_M=float(os.environ.get("PATROL_PROXIMITY_RADIUS_M", "5.0")),
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
        # Positions refresh roughly every EMIT_MIN_INTERVAL_S (1.8s, in
        # omada_ingest_service.py), so 120s is ~65 missed cycles — long enough
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
        COLLISION_DISTANCE_M=float(os.environ.get("COLLISION_DISTANCE_M", "2.0")),
        COLLISION_ALERT_SECONDS=int(os.environ.get("COLLISION_ALERT_SECONDS", "3")),
        MIN_DWELL_SECONDS=int(os.environ.get("MIN_DWELL_SECONDS", "30")),
        RSSI_NOISE_STD=float(os.environ.get("RSSI_NOISE_STD", "3.0")),
        # Behavioural cutoff for the single-AP proximity fallback: a beacon whose
        # strongest AP is fainter than this is "too far to be a useful anchor" and
        # is treated as gone (no write → record ages out → frontend drops marker).
        # Not a hardware sensitivity limit — the APs receive well below -90 dBm.
        # Tune after ceiling-mount and tx_power calibration.
        PROXIMITY_RSSI_FLOOR=float(os.environ.get("PROXIMITY_RSSI_FLOOR", "-90.0")),
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
    )


settings = _load()

# Rate limit strings (documentation & reuse in tests)
RATE_LIMIT_AUTH = "5/15minutes"
RATE_LIMIT_GENERAL = "100/minute"
RATE_LIMIT_TELEMETRY = "200/minute"
