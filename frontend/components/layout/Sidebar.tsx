"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useDashboardStore } from "@/store/dashboardStore";
import { subscribeToPendingCount } from "@/services/userService";
import { useAuth } from "@/hooks/useAuth";
import type { PositionRecord } from "@/types/position";
import type { AlertRecord } from "@/types/alert";

const NAV_ALL = [
  {
    href: "/dashboard", label: "Dashboard", adminOnly: false,
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>,
  },
  {
    href: "/dashboard/alerts", label: "Alerts", adminOnly: false,
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
  },
  {
    href: "/dashboard/reports", label: "Reports", adminOnly: false,
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>,
  },
  {
    href: "/dashboard/floor-plans", label: "Floor Plans", adminOnly: false,
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>,
  },
  {
    href: "/dashboard/beacons", label: "Beacons", adminOnly: true,
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/></svg>,
  },
  {
    href: "/dashboard/users", label: "Users", adminOnly: true,
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
  },
];

const ROLE_COLOUR: Record<string, string> = {
  guard: "text-s-success", worker: "text-blue-400", forklift: "text-s-accent",
};

const PERSON_TYPE_ORDER: { key: string; label: string }[] = [
  { key: "guard",    label: "Guards"    },
  { key: "worker",   label: "Workers"   },
  { key: "forklift", label: "Forklifts" },
];

function isRecent(ts: string) {
  return Date.now() - new Date(ts).getTime() < 60_000;
}

interface Props { collapsed: boolean; onToggle: () => void }

export default function Sidebar({ collapsed, onToggle }: Props) {
  const pathname = usePathname();
  const { userRecord } = useAuth();
  const isAdmin = userRecord?.role === "admin";
  const positions = useDashboardStore((s) => s.positions);
  const personnel = Object.values(positions) as PositionRecord[];
  const [pendingCount, setPendingCount] = useState(0);
  const alerts = useDashboardStore((s) => s.alerts);
  const activeAlertCount = Object.values(alerts as Record<string, AlertRecord>)
    .filter((a) => !a.resolved).length;

  useEffect(() => {
    if (!isAdmin) return;
    const unsub = subscribeToPendingCount(setPendingCount);
    return unsub;
  }, [isAdmin]);

  const navItems = NAV_ALL.filter(({ adminOnly }) => !adminOnly || isAdmin);

  return (
    <aside
      className="fixed left-0 top-14 bottom-0 z-30 flex flex-col transition-all duration-200"
      style={{
        width: collapsed ? 60 : 240,
        background: "var(--bg-base)",
      }}
    >
      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-4 h-6 w-6 rounded-full bg-s-elevated border border-s-border flex items-center justify-center text-s-muted hover:text-s-text z-10"
      >
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          {collapsed
            ? <polyline points="9 18 15 12 9 6" />
            : <polyline points="15 18 9 12 15 6" />}
        </svg>
      </button>

      {/* Nav */}
      <nav className={`pt-3 ${collapsed ? "flex flex-col items-center gap-2 px-2" : "flex flex-col gap-0.5 px-2"}`}>
        {navItems.map(({ href, label, icon }) => {
          const active = pathname === href;
          const isUsers  = href === "/dashboard/users";
          const isAlerts = href === "/dashboard/alerts";
          const badgeCount =
            isUsers  ? pendingCount :
            isAlerts ? activeAlertCount : 0;
          const showBadge = badgeCount > 0;

          if (collapsed) {
            return (
              <Link
                key={href}
                href={href}
                title={label}
                className={`relative h-11 w-11 rounded-full flex items-center justify-center transition-colors
                  ${active
                    ? "bg-s-accent text-white"
                    : "border border-s-border text-s-muted hover:bg-s-elevated hover:text-s-text"}`}
              >
                {icon}
                {showBadge && (
                  <span className="absolute top-0 right-0 h-3.5 w-3.5 rounded-full bg-s-accent flex items-center justify-center border-2 border-s-surface">
                    <span className="font-mono text-[7px] font-bold text-white leading-none">
                      {badgeCount > 9 ? "9+" : badgeCount}
                    </span>
                  </span>
                )}
              </Link>
            );
          }

          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 py-2.5 text-sm transition-colors
                ${active
                  ? "border-l-2 border-s-accent text-s-accent pl-[10px] pr-3"
                  : "text-s-muted hover:text-s-text hover:bg-s-elevated rounded-lg px-3"}`}
            >
              <span className="relative shrink-0">
                {icon}
                {showBadge && !active && (
                  <span className="absolute -top-1.5 -right-1.5 h-3.5 w-3.5 rounded-full bg-s-accent flex items-center justify-center">
                    <span className="font-mono text-[8px] font-bold text-s-base leading-none">
                      {badgeCount > 9 ? "9+" : badgeCount}
                    </span>
                  </span>
                )}
              </span>
              <span className="font-medium">{label}</span>
              {showBadge && (
                <span className="ml-auto h-4 min-w-4 px-1 rounded-full bg-s-accent flex items-center justify-center">
                  <span className="font-mono text-[9px] font-bold text-s-base leading-none">
                    {badgeCount > 9 ? "9+" : badgeCount}
                  </span>
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Personnel panel — expanded only */}
      {!collapsed && (
        <div className="flex-1 overflow-hidden flex flex-col mt-4 pt-2">
          <p className="px-3 py-1 text-[10px] font-mono text-s-muted tracking-widest uppercase">
            Personnel ({personnel.length})
          </p>
          <ul className="flex-1 overflow-y-auto px-2 pb-2">
            {personnel.length === 0 && (
              <li className="px-3 py-2 text-xs text-s-muted italic">No active personnel</li>
            )}
            {PERSON_TYPE_ORDER.map(({ key, label }) => {
              const group = personnel.filter((p) => p.person_type === key);
              if (group.length === 0) return null;
              return (
                <li key={key}>
                  <p className="px-2 pt-3 pb-1 text-[9px] font-mono text-s-muted tracking-widest uppercase">
                    {label} ({group.length})
                  </p>
                  <ul className="space-y-0.5">
                    {group.map((p) => (
                      <li
                        key={p.beacon_mac}
                        className="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-s-elevated cursor-default"
                      >
                        <span
                          className={`h-2 w-2 rounded-full shrink-0 ${
                            isRecent(p.timestamp) ? "bg-s-success" : "bg-s-muted"
                          }`}
                        />
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs truncate ${ROLE_COLOUR[p.person_type] ?? "text-s-text"}`}>
                            {p.label || p.person_id}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </aside>
  );
}
