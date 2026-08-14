"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { collection, onSnapshot, query } from "firebase/firestore";
import { fsdb } from "@/config/firebase";
import { useAuth } from "@/hooks/useAuth";
import { updateUserStatus, updateUserRole, deleteUser } from "@/services/userService";
import { signOut } from "@/services/authService";
import { toast } from "@/store/toastStore";
import type { UserRecord, UserStatus } from "@/types/user";
import { useDashboardStore } from "@/store/dashboardStore";

const GRID = "200px 280px 100px 120px 160px 180px";
const CELL = { display: "flex", alignItems: "center", padding: "10px 12px" } as const;

function badge(color: string) {
  return {
    color,
    background: `color-mix(in srgb, ${color} 15%, transparent)`,
    fontFamily: "IBM Plex Mono, monospace",
    fontSize: 10,
    padding: "2px 8px",
    borderRadius: 9999,
    whiteSpace: "nowrap",
  } as const;
}

function actionBtn(color: string) {
  return {
    color,
    background: `color-mix(in srgb, ${color} 15%, transparent)`,
    fontFamily: "IBM Plex Mono, monospace",
    fontSize: 10,
    padding: "3px 8px",
    borderRadius: 4,
    border: "none",
    cursor: "pointer",
  } as const;
}

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
  const { user, userRecord } = useAuth();
  const isOwner = userRecord?.role === "owner";
  const router = useRouter();
  const { cachedUsers, setCachedUsers } = useDashboardStore();
  const [users, setUsers] = useState<UserRecord[]>(cachedUsers);
  const [loading, setLoading] = useState(true);
  const [deleteTarget, setDeleteTarget] = useState<UserRecord | null>(null);
  const [loadingUserId, setLoadingUserId] = useState<string | null>(null);

  // Real-time listener — updates instantly when email_verified flips in Firestore
  useEffect(() => {
    const unsubscribe = onSnapshot(
      query(collection(fsdb, "users")),
      (snap) => {
        const all = snap.docs.map((d) => d.data() as UserRecord);
        const filtered = all
          .filter((u) => u.email_verified === true || u.status !== "pending")
          .sort((a, b) => b.created_at.localeCompare(a.created_at));
        setUsers(filtered);
        setCachedUsers(filtered);
        setLoading(false);
      },
      () => setLoading(false),
    );
    return () => unsubscribe();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleStatus(uid: string, status: UserStatus) {
    if (!user) return;
    try {
      const token = await user.getIdToken();
      await updateUserStatus(uid, status, token);
      toast.success(`User ${status}`);
    } catch {
      toast.error("Failed to update status");
    }
  }

  async function handlePromote(uid: string) {
    if (!user) return;
    try {
      const token = await user.getIdToken();
      await updateUserRole(uid, "admin", token);
      toast.success("User promoted to admin");
    } catch {
      toast.error("Failed to promote user");
    }
  }

  async function handleDemote(uid: string) {
    if (!user) return;
    try {
      const token = await user.getIdToken();
      await updateUserRole(uid, "user", token);
      toast.success("Admin demoted to user");
    } catch {
      toast.error("Failed to demote user");
    }
  }

  async function handleDelete() {
    if (!user || !deleteTarget) return;
    setLoadingUserId(deleteTarget.uid);
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
      }
    } catch {
      toast.error("Failed to remove user");
      setDeleteTarget(null);
    } finally {
      setLoadingUserId(null);
    }
  }

  if (loading) return (
    <div className="max-w-[1200px] mx-auto px-10 py-8 space-y-4">
      <div className="h-3 bg-s-elevated rounded w-36 animate-pulse" />
      <div className="bg-s-surface border border-s-border rounded-lg overflow-hidden overflow-x-auto">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: GRID }} className="border-b border-s-border/50 animate-pulse last:border-0">
            <div style={CELL}><div className="h-3 bg-s-elevated rounded w-full" /></div>
            <div style={CELL}><div className="h-3 bg-s-elevated rounded w-full" /></div>
            <div style={CELL}><div className="h-3 bg-s-elevated rounded w-12" /></div>
            <div style={CELL}><div className="h-3 bg-s-elevated rounded w-16" /></div>
            <div style={CELL}><div className="h-3 bg-s-elevated rounded w-20" /></div>
            <div style={CELL}><div className="h-3 bg-s-elevated rounded w-24" /></div>
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
          loading={loadingUserId === deleteTarget?.uid}
        />
      )}

      <div className="max-w-[1200px] mx-auto px-10 py-8 space-y-4">
        <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">
          User Management ({users.length})
        </h1>

        <div className="bg-s-surface border border-s-border rounded-lg overflow-hidden overflow-x-auto">
          {/* Header */}
          <div style={{ display: "grid", gridTemplateColumns: GRID, borderBottom: "1px solid var(--border)" }}>
            {["Name", "Email", "Role", "Status", "Person ID", "Actions"].map((h) => (
              <div key={h} style={{ ...CELL, color: "var(--text-secondary)", fontFamily: "IBM Plex Mono, monospace", fontSize: 10, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                {h}
              </div>
            ))}
          </div>

          {/* Rows */}
          {users.map((u) => {
            const isSelf = u.uid === user?.uid;
            const statusColor = u.status === "approved" ? "var(--success)" : u.status === "suspended" ? "var(--danger)" : "var(--text-secondary)";
            const roleColor = u.role === "owner" || u.role === "admin" ? "var(--accent)" : "var(--text-secondary)";
            return (
              <div
                key={u.uid}
                style={{ display: "grid", gridTemplateColumns: GRID, borderBottom: "1px solid var(--border)" }}
                className="hover:bg-s-elevated transition-colors"
              >
                {/* Name */}
                <div style={{ ...CELL, minWidth: 0 }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-primary)", fontWeight: 500, fontSize: 14 }}>
                    {u.display_name}
                  </span>
                  {isSelf && (
                    <span style={{ marginLeft: 8, fontFamily: "IBM Plex Mono, monospace", fontSize: 9, color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                      (you)
                    </span>
                  )}
                </div>

                {/* Email */}
                <div style={{ ...CELL, minWidth: 0 }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-secondary)", fontFamily: "IBM Plex Mono, monospace", fontSize: 14 }}>
                    {u.email}
                  </span>
                </div>

                {/* Role */}
                <div style={CELL}>
                  <span style={badge(roleColor)}>{u.role.toUpperCase()}</span>
                </div>

                {/* Status */}
                <div style={CELL}>
                  <span style={badge(statusColor)}>{u.status.toUpperCase()}</span>
                </div>

                {/* Person ID */}
                <div style={{ ...CELL, minWidth: 0 }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--text-secondary)", fontFamily: "IBM Plex Mono, monospace" }}>
                    {u.person_id || "—"}
                  </span>
                </div>

                {/* Actions */}
                <div style={{ ...CELL, gap: 6, flexWrap: "nowrap", whiteSpace: "nowrap" }}>
                  {u.status === "pending" && (
                    <button onClick={() => handleStatus(u.uid, "approved")} style={actionBtn("var(--success)")} className="hover:opacity-80 transition-opacity">
                      Approve
                    </button>
                  )}
                  {isOwner && u.role === "user" && u.status === "approved" && (
                    <button onClick={() => handlePromote(u.uid)} style={actionBtn("var(--accent)")} className="hover:opacity-80 transition-opacity">
                      Promote to Admin
                    </button>
                  )}
                  {isOwner && u.role === "admin" && (
                    <button onClick={() => handleDemote(u.uid)} style={actionBtn("var(--text-secondary)")} className="hover:opacity-80 transition-opacity">
                      Demote to User
                    </button>
                  )}
                  <button onClick={() => setDeleteTarget(u)} style={actionBtn("var(--danger)")} className="hover:opacity-80 transition-opacity">
                    {isSelf ? "Delete Account" : "Remove"}
                  </button>
                </div>
              </div>
            );
          })}

          {users.length === 0 && (
            <div className="text-center py-12 text-s-muted text-sm">No users found.</div>
          )}
        </div>
      </div>
    </>
  );
}
