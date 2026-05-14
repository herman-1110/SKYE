"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { signOut, resendVerificationEmail } from "@/services/authService";
import { toast } from "@/store/toastStore";

export default function PendingApprovalPage() {
  const router = useRouter();
  const [resending, setResending] = useState(false);

  async function handleSignOut() {
    await signOut();
    router.push("/login");
  }

  async function handleResend() {
    setResending(true);
    try {
      await resendVerificationEmail();
      toast.success("Verification email sent. Check your inbox.");
    } catch {
      toast.error("Failed to resend. Please try again.");
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="min-h-screen bg-s-base flex items-center justify-center px-4">
      <div className="max-w-sm w-full bg-s-surface border border-s-border rounded-xl p-8 text-center space-y-4">
        <div className="h-14 w-14 rounded-full bg-s-accent/10 border border-s-accent/30 flex items-center justify-center mx-auto">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-accent">
            <circle cx="12" cy="12" r="10"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <div>
          <h1 className="text-lg font-bold text-s-text">Awaiting Approval</h1>
          <p className="text-sm text-s-muted mt-1">
            Please check your email and verify your address before your account can be approved.
            Once verified, a Security Manager will grant you access.
          </p>
        </div>

        <div className="pt-1">
          <button
            onClick={handleResend}
            disabled={resending}
            className="w-full py-2 rounded-lg border border-s-border text-xs font-mono text-s-muted hover:text-s-text hover:border-s-accent disabled:opacity-40 transition-colors flex items-center justify-center gap-1.5"
          >
            {resending && <span className="h-3 w-3 rounded-full border-2 border-s-muted border-t-transparent animate-spin" />}
            {resending ? "Sending…" : "Resend verification email"}
          </button>
        </div>

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
