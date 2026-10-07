export type UserRole = "owner" | "admin" | "user";
export type UserStatus = "pending" | "approved" | "suspended";

// "owner" is a superset of "admin" everywhere admin-gated UI/behavior is
// decided — use this instead of a bare `role === "admin"` check so the owner
// never silently loses access a plain admin has.
export function isAdminRole(role: UserRole | undefined | null): boolean {
  return role === "admin" || role === "owner";
}

export interface UserRecord {
  uid: string;
  email: string;
  display_name: string;
  role: UserRole;
  status: UserStatus;
  person_id: string;
  created_at: string;
  email_verified?: boolean;
}
