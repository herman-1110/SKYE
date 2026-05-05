import { collection, doc, getDoc, onSnapshot, query, where } from "firebase/firestore";
import { fsdb } from "@/config/firebase";
import type { UserRecord, UserRole, UserStatus } from "@/types/user";

export async function getUserRecord(uid: string): Promise<UserRecord | null> {
  const snap = await getDoc(doc(fsdb, "users", uid));
  return snap.exists() ? (snap.data() as UserRecord) : null;
}

export async function registerUser(
  email: string,
  password: string,
  displayName: string,
  personId = ""
): Promise<{ uid: string; role: string; status: string }> {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name: displayName, person_id: personId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail ?? "Registration failed");
  }
  return res.json();
}

export async function getUsers(token: string): Promise<UserRecord[]> {
  const res = await fetch("/api/users", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function getPendingUsers(token: string): Promise<UserRecord[]> {
  const res = await fetch("/api/users/pending", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to fetch pending users");
  return res.json();
}

export async function updateUserStatus(uid: string, status: UserStatus, token: string): Promise<void> {
  const res = await fetch(`/api/users/${uid}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error("Failed to update status");
}

export async function updateUserRole(uid: string, role: UserRole, token: string): Promise<void> {
  const res = await fetch(`/api/users/${uid}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) throw new Error("Failed to update role");
}

export async function deleteUser(uid: string, token: string): Promise<void> {
  const res = await fetch(`/api/users/${uid}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to delete user");
}

export function subscribeToPendingCount(callback: (count: number) => void): () => void {
  const q = query(collection(fsdb, "users"), where("status", "==", "pending"));
  return onSnapshot(q, (snap) => callback(snap.size));
}
