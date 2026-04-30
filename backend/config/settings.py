import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    FIREBASE_KEY_PATH: str
    FIREBASE_DATABASE_URL: str
    GEMINI_API_KEY: str
    PORT: int
    DEBUG: bool
    OMADA_ACCESS_TOKEN: str
    PATH_LOSS_EXPONENT: float
    TX_POWER_DEFAULT: float
    MAN_DOWN_MINUTES: int
    MAN_DOWN_MOVEMENT_THRESHOLD: float
    COLLISION_ALERT_SECONDS: int
    MIN_DWELL_SECONDS: int
    RSSI_NOISE_STD: float


def _load() -> Settings:
    return Settings(
        FIREBASE_KEY_PATH=os.environ["FIREBASE_KEY_PATH"],
        FIREBASE_DATABASE_URL=os.environ["FIREBASE_DATABASE_URL"],
        GEMINI_API_KEY=os.environ["GEMINI_API_KEY"],
        PORT=int(os.environ.get("PORT", "5000")),
        DEBUG=os.environ.get("DEBUG", "false").lower() == "true",
        OMADA_ACCESS_TOKEN=os.environ["OMADA_ACCESS_TOKEN"],
        PATH_LOSS_EXPONENT=float(os.environ.get("PATH_LOSS_EXPONENT", "2.5")),
        TX_POWER_DEFAULT=float(os.environ.get("TX_POWER_DEFAULT", "-59")),
        MAN_DOWN_MINUTES=int(os.environ.get("MAN_DOWN_MINUTES", "5")),
        MAN_DOWN_MOVEMENT_THRESHOLD=float(os.environ.get("MAN_DOWN_MOVEMENT_THRESHOLD", "1.0")),
        COLLISION_ALERT_SECONDS=int(os.environ.get("COLLISION_ALERT_SECONDS", "3")),
        MIN_DWELL_SECONDS=int(os.environ.get("MIN_DWELL_SECONDS", "30")),
        RSSI_NOISE_STD=float(os.environ.get("RSSI_NOISE_STD", "3.0")),
    )


settings = _load()
