from dataclasses import dataclass


@dataclass
class UserRecord:
    uid: str           # Firebase Auth UID — also the Firestore document ID
    email: str
    display_name: str
    role: str          # "admin" | "user"
    status: str        # "pending" | "approved" | "suspended"
    person_id: str     # BLE beacon person_id that maps this account to a position track
    created_at: str    # ISO 8601
