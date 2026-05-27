from dataclasses import asdict
from typing import Optional

from firebase_admin import firestore

from models.user import UserRecord
from utils.timestamp_utils import utcnow_iso

_VALID_ROLES = {"admin", "user"}
_VALID_STATUSES = {"pending", "approved", "suspended"}


class UserRepository:
    def _col(self):
        return firestore.client().collection("users")

    def create(self, uid: str, email: str, display_name: str, person_id: str = "", email_verified: bool = False) -> UserRecord:
        """Create a user doc. The first user ever gets role=admin and status=approved automatically."""
        existing = list(self._col().limit(1).stream())
        is_first = len(existing) == 0
        role = "admin" if is_first else "user"
        status = "approved" if is_first else "pending"

        print(f"[user_repository.create] uid={uid} is_first={is_first} role={role} status={status}")

        record = UserRecord(
            uid=uid,
            email=email,
            display_name=display_name,
            role=role,
            status=status,
            person_id=person_id,
            created_at=utcnow_iso(),
            email_verified=email_verified,
        )
        self._col().document(uid).set(asdict(record))
        return record

    def get_by_uid(self, uid: str) -> Optional[UserRecord]:
        """Return UserRecord for a given Firebase Auth UID, or None if not found."""
        snap = self._col().document(uid).get()
        if not snap.exists:
            return None
        d = snap.to_dict()
        return UserRecord(**d)

    def get_all(self) -> list[UserRecord]:
        """Return all users ordered by created_at descending."""
        docs = self._col().order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        return [UserRecord(**d.to_dict()) for d in docs]

    def get_pending(self) -> list[UserRecord]:
        """Return all users where status == pending."""
        docs = self._col().where("status", "==", "pending").stream()
        return [UserRecord(**d.to_dict()) for d in docs]

    def update_role(self, uid: str, role: str) -> None:
        """Update the role field. Validates role is admin or user."""
        if role not in _VALID_ROLES:
            raise ValueError(f"Invalid role: {role}")
        self._col().document(uid).update({"role": role})

    def update_status(self, uid: str, status: str) -> None:
        """Update the status field. Validates status is pending/approved/suspended."""
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        self._col().document(uid).update({"status": status})

    def update_person_id(self, uid: str, person_id: str) -> None:
        """Update the BLE person_id mapping for this user."""
        self._col().document(uid).update({"person_id": person_id})

    def update_email_verified(self, uid: str, value: bool) -> None:
        """Mark a user's email as verified in Firestore."""
        self._col().document(uid).update({"email_verified": value})

    def delete(self, uid: str) -> None:
        """Delete the Firestore users/{uid} document."""
        self._col().document(uid).delete()


user_repository = UserRepository()
