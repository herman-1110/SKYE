"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { getUsers, updateUserStatus, updateUserRole, deleteUser } from "@/services/userService";
import { signOut } from "@/services/authService";
import { toast } from "@/store/toastStore";
import type { UserRecord, UserStatus, UserRole } from "@/types/user";
import { useDashboardStore } from "@/store/dashboardStore";

const STATUS_COLOURS: Record<UserStatus, string> = {
  approved: "bg-s-success/20 text-s-success",
  pending:  "bg-s-accent/20 text-s-accent",
  suspended:"bg-s-danger/20 text-s-danger",
};

const ROLE_COLOURS: Record<UserRole, string> = {
  admin: "bg-s-accent/20 text-s-accent",
  user:  "bg-s-muted/20 text-s-muted",
};

function DeleteModal({ target, isSelf, onCancel, onConfirm, loading }: {
  target: UserRecord;
  isSelf: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  loading: boolean;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape" && !loading) onCancel(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onCancel, loading]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget && !loading) onCancel(); }}
    >
      <div className="rounded-xl p-6 max-w-sm w-full mx-4 space-y-4"
        style={{ background: "var(--glass-bg)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", border: "1px solid var(--glass-border)", boxShadow: "var(--glass-shadow)" }}
      >
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-full bg-s-danger/10 flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-s-danger">
              <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
            </svg>
          </div>
          <h2 className="text-sm font-bold text-s-text">
            {isSelf ? "Delete Account" : `Remove ${target.display_name}`}
          </h2>
        </div>
        <p className="text-xs text-s-muted leading-relaxed">
          {isSelf
            ? "Are you sure you want to delete your account? This action cannot be undone. You will be signed out immediately."
            : `Are you sure you want to remove ${target.display_name} (${target.email})? This action cannot be undone.`}
        </p>
        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-medium text-s-muted hover:text-s-text hover:bg-s-elevated transition-colors disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className="px-3 py-1.5 rounded-lg text-xs font-bold bg-s-danger text-white hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center gap-1.5"
          >
            {loading && <span className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />}
            {isSelf ? "Delete Account" : "Remove User"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function UsersPage() {
  const { user } = useAuth();
  const router = useRouter();
  const { cachedUsers, setCachedUsers } = useDashboardStore();
  const [users, setUsers] = useState<UserRecord[]>(cachedUsers);
  const [loading, setLoading] = useState(cachedUsers.length === 0);
  const [deleteTarget, setDeleteTarget] = useState<UserRecord | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  async function load() {
    if (!user) return;
    const token = await user.getIdToken();
    const data = await getUsers(token);
    setUsers(data);
    setCachedUsers(data);
    setLoading(false);
  }

  useEffect(() => {
    if (cachedUsers.length === 0) load();
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

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

  async function handleDelete() {
    if (!user || !deleteTarget) return;
    setDeleteLoading(true);
    const isSelf = deleteTarget.uid === user.uid;
    try {
      const token = await user.getIdToken();
      await deleteUser(deleteTarget.uid, token);
      if (isSelf) {
        await signOut();
        router.push("/login");
      } else {
        toast.success(`${deleteTarget.display_name} removed`);
        setDeleteTarget(null);
        await load();
      }
    } catch {
      toast.error("Failed to remove user");
      setDeleteLoading(false);
      setDeleteTarget(null);
    }
  }

  if (loading) return (
    <div className="max-w-[1200px] mx-auto px-10 py-8 space-y-4">
      <div className="h-3 bg-s-elevated rounded w-36 animate-pulse" />
      <div className="bg-s-surface border border-s-border rounded-lg overflow-hidden">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="flex gap-4 px-4 py-3.5 border-b border-s-border/50 animate-pulse last:border-0">
            <div className="h-3 bg-s-elevated rounded flex-1" />
            <div className="h-3 bg-s-elevated rounded flex-1" />
            <div className="h-3 bg-s-elevated rounded w-16" />
            <div className="h-3 bg-s-elevated rounded w-20" />
            <div className="h-3 bg-s-elevated rounded w-16" />
            <div className="h-3 bg-s-elevated rounded w-24" />
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <>
      {deleteTarget && (
        <DeleteModal
          target={deleteTarget}
          isSelf={deleteTarget.uid === user?.uid}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
          loading={deleteLoading}
        />
      )}

      <div className="max-w-[1200px] mx-auto px-10 py-8 space-y-4">
        <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">
          User Management ({users.length})
        </h1>

        <div className="bg-s-surface border border-s-border rounded-lg overflow-hidden">
          <table className="w-full text-xs" style={{ borderCollapse: 'collapse', tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '200px' }} />
              <col style={{ width: '240px' }} />
              <col style={{ width: '100px' }} />
              <col style={{ width: '100px' }} />
              <col style={{ width: '140px' }} />
              <col style={{ minWidth: '200px' }} />
            </colgroup>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {["Name", "Email", "Role", "Status", "Person ID", "Actions"].map((h) => (
                  <th key={h} style={{ textAlign: 'left', color: 'var(--text-secondary)', padding: '8px 12px', fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const isSelf = u.uid === user?.uid;
                return (
                  <tr key={u.uid} style={{ borderBottom: '1px solid var(--border)' }} className="hover:bg-s-elevated transition-colors">
                    <td style={{ padding: '10px 12px', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} className="font-medium">
                      {u.display_name}
                      {isSelf && <span className="ml-2 font-mono text-[9px] text-s-muted">(you)</span>}
                    </td>
                    <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} className="font-mono">{u.email}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <span className={`font-mono text-[10px] px-2 py-0.5 rounded-full ${ROLE_COLOURS[u.role]}`}>
                        {u.role.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span className={`font-mono text-[10px] px-2 py-0.5 rounded-full ${STATUS_COLOURS[u.status]}`}>
                        {u.status.toUpperCase()}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} className="font-mono">{u.person_id || "—"}</td>
                    <td style={{ padding: '10px 12px' }}>
                      <div className="flex gap-2 flex-wrap">
                        {/* Approve pending */}
                        {u.status === "pending" && (
                          <button
                            onClick={() => handleStatus(u.uid, "approved")}
                            className="px-2 py-1 rounded bg-s-success/20 text-s-success font-mono text-[10px] hover:bg-s-success/30 transition-colors"
                          >
                            Approve
                          </button>
                        )}

                        {/* Suspend / Unsuspend — hidden for self */}
                        {!isSelf && (
                          u.status === "suspended" ? (
                            <button
                              onClick={() => handleStatus(u.uid, "approved")}
                              className="px-2 py-1 rounded bg-s-success/20 text-s-success font-mono text-[10px] hover:bg-s-success/30 transition-colors"
                            >
                              Unsuspend
                            </button>
                          ) : (
                            <button
                              onClick={() => handleStatus(u.uid, "suspended")}
                              className="px-2 py-1 rounded bg-s-danger/20 text-s-danger font-mono text-[10px] hover:bg-s-danger/30 transition-colors"
                            >
                              Suspend
                            </button>
                          )
                        )}

                        {/* Role toggle — Demote hidden for self */}
                        {u.role === "user" ? (
                          <button
                            onClick={() => handleRole(u.uid, "admin")}
                            className="px-2 py-1 rounded bg-s-accent/20 text-s-accent font-mono text-[10px] hover:bg-s-accent/30 transition-colors"
                          >
                            Make Admin
                          </button>
                        ) : (
                          !isSelf && (
                            <button
                              onClick={() => handleRole(u.uid, "user")}
                              className="px-2 py-1 rounded bg-s-muted/20 text-s-muted font-mono text-[10px] hover:bg-s-muted/30 transition-colors"
                            >
                              Demote
                            </button>
                          )
                        )}

                        {/* Remove (other users) / Delete Account (self) */}
                        <button
                          onClick={() => setDeleteTarget(u)}
                          className="px-2 py-1 rounded bg-s-danger/20 text-s-danger font-mono text-[10px] hover:bg-s-danger/30 transition-colors"
                        >
                          {isSelf ? "Delete Account" : "Remove"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {users.length === 0 && (
            <div className="text-center py-12 text-s-muted text-sm">No users found.</div>
          )}
        </div>
      </div>
    </>
  );
}
