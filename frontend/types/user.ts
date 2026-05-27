export type UserRole = "admin" | "user";
export type UserStatus = "pending" | "approved" | "suspended";

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
