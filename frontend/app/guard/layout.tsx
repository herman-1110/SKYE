"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { FullScreenLoader } from "@/components/shared/LoadingSpinner";
import ToastContainer from "@/components/shared/ToastContainer";

export default function GuardLayout({ children }: { children: React.ReactNode }) {
  const { user, userRecord, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!user) { router.push("/login"); return; }
    // Admins go to the full dashboard, not the guard view
    if (userRecord?.role === "admin") router.push("/dashboard");
  }, [user, userRecord, isLoading, router]);

  if (isLoading) return <FullScreenLoader />;
  if (!user || userRecord?.role === "admin") return null;

  return (
    <div className="min-h-screen bg-s-base">
      {/* Minimal top bar */}
      <header className="fixed top-0 inset-x-0 h-14 bg-s-surface border-b border-s-border flex items-center px-4 gap-3 z-50">
        <div className="h-7 w-7 rounded-md bg-s-accent flex items-center justify-center">
          <span className="font-mono font-bold text-sm text-s-base">S</span>
        </div>
        <span className="font-bold text-s-text text-sm tracking-wide">SKYE</span>
        <span className="font-mono text-xs text-s-muted ml-1">/ Guard View</span>
        <div className="ml-auto flex items-center gap-3">
          <span className="font-mono text-xs text-s-muted">{userRecord?.display_name}</span>
          <span className="h-2 w-2 rounded-full bg-s-success animate-pulse" />
        </div>
      </header>
      <main className="pt-14 p-4">
        {children}
      </main>
      <ToastContainer />
    </div>
  );
}
