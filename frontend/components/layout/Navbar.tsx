"use client";
import { usePathname, useRouter } from "next/navigation";
import { signOut } from "@/services/authService";
import { useDashboardStore } from "@/store/dashboardStore";
import StatusBadge from "@/components/shared/StatusBadge";
import type { User } from "firebase/auth";

const PAGE_TITLES: Record<string, string> = {
  "/dashboard":             "Command Dashboard",
  "/dashboard/alerts":      "Alert Management",
  "/dashboard/reports":     "Audit Reports",
  "/dashboard/floor-plans": "Floor Plans",
  "/dashboard/users":       "User Management",
};

function initials(email: string): string {
  return email.split("@")[0].slice(0, 2).toUpperCase();
}

export default function Navbar({ user }: { user: User }) {
  const pathname = usePathname();
  const router = useRouter();
  const activeShiftId = useDashboardStore((s) => s.activeShiftId);
  const title = PAGE_TITLES[pathname] ?? "Dashboard";

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  return (
    <header className="fixed top-0 left-0 right-0 h-14 z-40 bg-s-surface border-b border-s-border flex items-center px-4 gap-4">
      {/* Logo */}
      <div className="flex items-center gap-2 w-[240px] shrink-0">
        <div className="h-7 w-7 rounded bg-s-accent flex items-center justify-center">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-s-base">
            <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>
          </svg>
        </div>
        <span className="font-semibold text-s-text tracking-wide">SKYE</span>
      </div>

      {/* Page title */}
      <div className="flex-1 text-center">
        <span className="text-sm font-medium text-s-muted tracking-widest uppercase">{title}</span>
      </div>

      {/* Right */}
      <div className="flex items-center gap-3 w-[240px] justify-end">
        <StatusBadge status={activeShiftId ? "shift-active" : "no-shift"} />
        <div className="h-7 w-7 rounded-full bg-s-elevated border border-s-border flex items-center justify-center">
          <span className="font-mono text-[10px] text-s-muted">{initials(user.email ?? "U")}</span>
        </div>
        <button
          onClick={handleSignOut}
          className="p-1.5 rounded hover:bg-s-elevated text-s-muted hover:text-s-text transition-colors"
          title="Sign out"
          aria-label="Sign out"
        >
          {/* logout icon */}
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
          </svg>
        </button>
      </div>
    </header>
  );
}
