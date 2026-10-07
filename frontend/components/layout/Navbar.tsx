"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { signOut } from "@/services/authService";
import { useAuth } from "@/hooks/useAuth";
import { useThemeStore } from "@/store/themeStore";
import { isAdminRole } from "@/types/user";
import type { User } from "firebase/auth";

const PAGE_TITLES: Record<string, string> = {
  "/dashboard":             "Command Dashboard",
  "/dashboard/alerts":      "Alert Management",
  "/dashboard/reports":     "Audit Reports",
  "/dashboard/floor-plans": "Floor Plans",
  "/dashboard/users":       "User Management",
};

function SunIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  );
}

function GearIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>
  );
}

export default function Navbar({ user }: { user: User }) {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, toggleTheme } = useThemeStore();
  const { userRecord } = useAuth();
  const isAdmin = isAdminRole(userRecord?.role);
  const title = PAGE_TITLES[pathname] ?? "Dashboard";

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  return (
    <header className="fixed top-0 left-0 right-0 h-14 z-[100] flex items-center px-4 gap-4" style={{ background: "var(--bg-base)", backdropFilter: "blur(8px)", WebkitBackdropFilter: "blur(8px)" }}>
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

      {/* Right actions */}
      <div className="flex items-center gap-2 w-[300px] justify-end">
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label="Toggle theme"
          className="h-9 w-9 flex items-center justify-center rounded-full bg-s-elevated border border-s-border text-s-muted hover:border-s-accent hover:text-s-text transition-colors"
        >
          {theme === "dark" ? <SunIcon /> : <MoonIcon />}
        </button>

        {/* Safety settings (admin only) */}
        {isAdmin && (
          <Link
            href="/dashboard/safety-settings"
            title="Safety settings"
            aria-label="Safety settings"
            className="h-9 w-9 flex items-center justify-center rounded-full bg-s-elevated border border-s-border text-s-muted hover:border-s-accent hover:text-s-text transition-colors"
          >
            <GearIcon />
          </Link>
        )}

        {/* Sign out */}
        <button
          onClick={handleSignOut}
          className="p-1.5 rounded hover:bg-s-elevated text-s-muted hover:text-s-text transition-colors"
          title="Sign out"
          aria-label="Sign out"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </button>
      </div>
    </header>
  );
}
