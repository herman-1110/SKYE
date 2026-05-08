"use client";
import { useRouter } from "next/navigation";
import { signOut } from "@/services/authService";

export default function PendingApprovalPage() {
  const router = useRouter();

  async function handleSignOut() {
    await signOut();
    router.push("/login");
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
            Your account is pending approval by the Security Manager.
            You will be granted access once approved.
          </p>
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
