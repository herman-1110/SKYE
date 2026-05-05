"use client";
import { useRouter } from "next/navigation";
import { signOut } from "@/services/authService";

export default function SuspendedPage() {
  const router = useRouter();

  async function handleSignOut() {
    await signOut();
    router.push("/login");
  }

  return (
    <div className="min-h-screen bg-s-base flex items-center justify-center px-4">
      <div className="max-w-sm w-full bg-s-surface border border-s-danger/40 rounded-xl p-8 text-center space-y-4">
        <div className="h-14 w-14 rounded-full bg-s-danger/10 border border-s-danger/30 flex items-center justify-center mx-auto">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-danger">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <div>
          <h1 className="text-lg font-bold text-s-danger">Account Suspended</h1>
          <p className="text-sm text-s-muted mt-1">
            Your account has been suspended. Contact your Security Manager for assistance.
          </p>
        </div>
        <p className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
          SKYE Sentinel-AI · Access Denied
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
