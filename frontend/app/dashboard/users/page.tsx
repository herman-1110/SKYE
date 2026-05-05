"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getUsers, updateUserStatus, updateUserRole } from "@/services/userService";
import { toast } from "@/store/toastStore";
import type { UserRecord, UserStatus, UserRole } from "@/types/user";

const STATUS_COLOURS: Record<UserStatus, string> = {
  approved: "bg-s-success/20 text-s-success",
  pending: "bg-s-accent/20 text-s-accent",
  suspended: "bg-s-danger/20 text-s-danger",
};

const ROLE_COLOURS: Record<UserRole, string> = {
  admin: "bg-s-accent/20 text-s-accent",
  user: "bg-s-muted/20 text-s-muted",
};

export default function UsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    if (!user) return;
    const token = await user.getIdToken();
    const data = await getUsers(token);
    setUsers(data);
    setLoading(false);
  }

  useEffect(() => { load(); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleStatus(uid: string, status: UserStatus) {
    if (!user) return;
    try {
      const token = await user.getIdToken();
      await updateUserStatus(uid, status, token);
      toast.success(`User ${status}`);
      await load();
    } catch {
      toast.error("Failed to update status");
    }
  }

  async function handleRole(uid: string, role: UserRole) {
    if (!user) return;
    try {
      const token = await user.getIdToken();
      await updateUserRole(uid, role, token);
      toast.success("Role updated");
      await load();
    } catch {
      toast.error("Failed to update role");
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <span className="h-6 w-6 rounded-full border-2 border-s-accent border-t-transparent animate-spin" />
    </div>
  );

  return (
    <div className="max-w-[1200px] space-y-4">
      <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">
        User Management ({users.length})
      </h1>

      <div className="bg-s-surface border border-s-border rounded-lg overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-s-border">
              {["Name", "Email", "Role", "Status", "Person ID", "Actions"].map((h) => (
                <th key={h} className="font-mono text-[10px] text-s-muted tracking-widest uppercase text-left px-4 py-3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.uid} className="border-b border-s-border/50 hover:bg-s-elevated transition-colors">
                <td className="px-4 py-3 text-s-text font-medium">{u.display_name}</td>
                <td className="px-4 py-3 text-s-muted font-mono">{u.email}</td>
                <td className="px-4 py-3">
                  <span className={`font-mono text-[10px] px-2 py-0.5 rounded-full ${ROLE_COLOURS[u.role]}`}>
                    {u.role.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`font-mono text-[10px] px-2 py-0.5 rounded-full ${STATUS_COLOURS[u.status]}`}>
                    {u.status.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-3 text-s-muted font-mono">{u.person_id || "—"}</td>
                <td className="px-4 py-3">
                  <div className="flex gap-2">
                    {u.status === "pending" && (
                      <button
                        onClick={() => handleStatus(u.uid, "approved")}
                        className="px-2 py-1 rounded bg-s-success/20 text-s-success font-mono text-[10px] hover:bg-s-success/30 transition-colors"
                      >
                        Approve
                      </button>
                    )}
                    {u.status !== "suspended" && (
                      <button
                        onClick={() => handleStatus(u.uid, "suspended")}
                        className="px-2 py-1 rounded bg-s-danger/20 text-s-danger font-mono text-[10px] hover:bg-s-danger/30 transition-colors"
                      >
                        Suspend
                      </button>
                    )}
                    {u.role === "user" ? (
                      <button
                        onClick={() => handleRole(u.uid, "admin")}
                        className="px-2 py-1 rounded bg-s-accent/20 text-s-accent font-mono text-[10px] hover:bg-s-accent/30 transition-colors"
                      >
                        Make Admin
                      </button>
                    ) : (
                      <button
                        onClick={() => handleRole(u.uid, "user")}
                        className="px-2 py-1 rounded bg-s-muted/20 text-s-muted font-mono text-[10px] hover:bg-s-muted/30 transition-colors"
                      >
                        Demote
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && (
          <div className="text-center py-12 text-s-muted text-sm">No users found.</div>
        )}
      </div>
    </div>
  );
}
