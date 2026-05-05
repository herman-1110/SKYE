import re

from firebase_admin import auth as firebase_auth

from models.user import UserRecord
from repositories.user_repository import user_repository

_PW_ERROR = (
    "Password must be at least 8 characters and contain uppercase, "
    "lowercase, number, and special character"
)


class UserService:
    def register(self, email: str, password: str, display_name: str, person_id: str = "") -> UserRecord:
        """Create Firebase Auth account then persist Firestore user doc."""
        self._validate_password_strength(password)
        fb_user = firebase_auth.create_user(email=email, password=password, display_name=display_name)
        return user_repository.create(fb_user.uid, email, display_name, person_id)

    def _validate_password_strength(self, password: str) -> None:
        """Enforce minimum password strength — safety net independent of frontend checks."""
        if (
            len(password) < 8
            or not re.search(r"[A-Z]", password)
            or not re.search(r"[a-z]", password)
            or not re.search(r"[0-9]", password)
            or not re.search(r"[^A-Za-z0-9]", password)
        ):
            raise ValueError(_PW_ERROR)

    def approve(self, uid: str, approver_uid: str) -> None:
        """Set status=approved. Approver must be admin."""
        self._assert_admin(approver_uid)
        user_repository.update_status(uid, "approved")

    def reject(self, uid: str, approver_uid: str) -> None:
        """Set status=suspended (reject). Approver must be admin."""
        self._assert_admin(approver_uid)
        user_repository.update_status(uid, "suspended")

    def change_role(self, uid: str, new_role: str, approver_uid: str) -> None:
        """Change role. Approver must be admin."""
        self._assert_admin(approver_uid)
        user_repository.update_role(uid, new_role)

    def suspend(self, uid: str, approver_uid: str) -> None:
        """Set status=suspended. Approver must be admin."""
        self._assert_admin(approver_uid)
        user_repository.update_status(uid, "suspended")

    def get_all(self) -> list:
        """Return all users ordered by created_at descending."""
        return user_repository.get_all()

    def get_pending(self) -> list:
        """Return all users with status=pending."""
        return user_repository.get_pending()

    def update_role(self, uid: str, role: str, approver_uid: str) -> None:
        """Update role. Approver must be admin."""
        self._assert_admin(approver_uid)
        user_repository.update_role(uid, role)

    def update_status(self, uid: str, status: str, approver_uid: str) -> None:
        """Update status. Approver must be admin."""
        self._assert_admin(approver_uid)
        user_repository.update_status(uid, status)

    def register_google(self, uid: str, email: str, display_name: str) -> UserRecord:
        """Upsert via Google sign-in: return existing record if found, else create new one."""
        existing = user_repository.get_by_uid(uid)
        if existing:
            return existing
        return user_repository.create(uid, email, display_name)

    def _assert_admin(self, uid: str) -> None:
        user = user_repository.get_by_uid(uid)
        if user is None or user.role != "admin":
            raise PermissionError("Admin access required")


user_service = UserService()
