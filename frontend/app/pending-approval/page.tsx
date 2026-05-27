"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { auth } from "@/config/firebase";
import { signOut, resendVerificationEmail, syncEmailVerified } from "@/services/authService";
import { toast } from "@/store/toastStore";

export default function PendingApprovalPage() {
  const router = useRouter();
  const [emailVerified, setEmailVerified] = useState(false);
  const [userEmail, setUserEmail]         = useState<string | null>(null);
  const [isSyncing, setIsSyncing]         = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  const pollRef    = useRef<ReturnType<typeof setInterval> | null>(null);
  const syncDone   = useRef(false);
  const isSyncingR = useRef(false); // ref-based guard avoids stale closure

  async function runSync() {
    if (syncDone.current || isSyncingR.current) return;
    isSyncingR.current = true;
    setIsSyncing(true);
    try {
      const u = auth.currentUser;
      if (!u) return;
      console.log("[verify-email] Calling verify-email endpoint for uid:", u.uid);
      await syncEmailVerified(); // token force-refresh happens inside
      syncDone.current = true;
      console.log("[verify-email] Sync complete for uid:", u.uid);
    } catch (err) {
      console.error("[verify-email] Sync failed:", err);
    } finally {
      isSyncingR.current = false;
      setIsSyncing(false);
    }
  }

  useEffect(() => {
    const u = auth.currentUser;
    if (!u) return;

    setUserEmail(u.email);

    // Already verified on mount (page refresh after clicking the link)
    if (u.emailVerified) {
      setEmailVerified(true);
      runSync();
      return;
    }

    // Poll every 3s — reload() fetches fresh state from Firebase
    pollRef.current = setInterval(async () => {
      const current = auth.currentUser;
      if (!current) return;
      try {
        await current.reload();
      } catch {
        return; // network error — keep polling
      }
      // Re-read after reload so emailVerified reflects the latest fetched state
      const fresh = auth.currentUser;
      if (fresh?.emailVerified) {
        clearInterval(pollRef.current!);
        setEmailVerified(true);
        await runSync();
      }
    }, 3000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSignOut() {
    await signOut();
    router.push("/login");
  }

  async function handleResend() {
    if (resendCooldown > 0) return;
    try {
      await resendVerificationEmail();
      toast.success("Verification email sent. Check your inbox.");
      setResendCooldown(60);
      const timer = setInterval(() => {
        setResendCooldown((prev) => {
          if (prev <= 1) { clearInterval(timer); return 0; }
          return prev - 1;
        });
      }, 1000);
    } catch {
      toast.error("Failed to resend. Please try again.");
    }
  }

  return (
    <div className="min-h-screen bg-s-base flex items-center justify-center px-4">
      <div className="max-w-sm w-full bg-s-surface border border-s-border rounded-xl p-8 text-center space-y-4">

        {!emailVerified ? (
          <>
            <div className="h-14 w-14 rounded-full bg-s-accent/10 border border-s-accent/30 flex items-center justify-center mx-auto">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-accent">
                <rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-s-text">Verify your email</h1>
              <p className="text-sm text-s-muted mt-1">
                A verification link was sent to{" "}
                {userEmail && <strong className="text-s-text">{userEmail}</strong>}.
                {" "}Check your inbox and spam folder, then click the link.
              </p>
            </div>

            <p className="font-mono text-[10px] text-s-muted tracking-widest">
              CHECKING EVERY 3 SECONDS…
            </p>

            <div className="pt-1">
              <button
                onClick={handleResend}
                disabled={resendCooldown > 0}
                className="w-full py-2 rounded-lg border border-s-border text-xs font-mono text-s-muted hover:text-s-text hover:border-s-accent disabled:opacity-40 transition-colors"
              >
                {resendCooldown > 0
                  ? `Resend available in ${resendCooldown}s`
                  : "Resend verification email"}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="h-14 w-14 rounded-full bg-s-success/10 border border-s-success/30 flex items-center justify-center mx-auto">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-success">
                <circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold text-s-text">Email verified</h1>
              <p className="text-sm text-s-muted mt-1">
                Your account request has been submitted. A Security Manager will review it shortly.
              </p>
            </div>
            {isSyncing && (
              <p className="font-mono text-[10px] text-s-muted tracking-widest">SYNCING…</p>
            )}
          </>
        )}

        <p className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
          SKYE Sentinel-AI · Restricted Access
        </p>
        <button
          onClick={handleSignOut}
          className="text-xs text-s-muted hover:text-s-text transition-colors font-mono"
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
