"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useDashboardStore } from "@/store/dashboardStore";
import type { PositionRecord } from "@/types/position";

const NAV = [
  {
    href: "/dashboard", label: "Dashboard",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>,
  },
  {
    href: "/dashboard/alerts", label: "Alerts",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>,
  },
  {
    href: "/dashboard/reports", label: "Reports",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>,
  },
  {
    href: "/dashboard/floor-plans", label: "Floor Plans",
    icon: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>,
  },
];

const ROLE_COLOUR: Record<string, string> = {
  guard: "text-s-success", worker: "text-blue-400", forklift: "text-s-accent",
};

function isRecent(ts: string) {
  return Date.now() - new Date(ts).getTime() < 60_000;
}

interface Props { collapsed: boolean; onToggle: () => void }

export default function Sidebar({ collapsed, onToggle }: Props) {
  const pathname = usePathname();
  const positions = useDashboardStore((s) => s.positions);
  const personnel = Object.values(positions) as PositionRecord[];

  return (
    <aside
      className="fixed left-0 top-14 bottom-0 z-30 bg-s-surface border-r border-s-border flex flex-col transition-all duration-200"
      style={{ width: collapsed ? 60 : 240 }}
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
      <nav className="p-2 space-y-1 pt-3">
        {NAV.map(({ href, label, icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors
                ${active
                  ? "border-l-2 border-s-accent text-s-accent bg-s-elevated pl-[10px]"
                  : "text-s-muted hover:text-s-text hover:bg-s-elevated"}`}
              title={collapsed ? label : undefined}
            >
              <span className="shrink-0">{icon}</span>
              {!collapsed && <span className="font-medium">{label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Personnel panel */}
      {!collapsed && (
        <div className="flex-1 overflow-hidden flex flex-col border-t border-s-border mt-2 pt-2">
          <p className="px-3 py-1 text-[10px] font-mono text-s-muted tracking-widest uppercase">
            Personnel ({personnel.length})
          </p>
          <ul className="flex-1 overflow-y-auto px-2 space-y-0.5 pb-2">
            {personnel.length === 0 && (
              <li className="px-3 py-2 text-xs text-s-muted italic">No active personnel</li>
            )}
            {personnel.map((p) => (
              <li key={p.beacon_mac} className="flex items-center gap-2 px-2 py-2 rounded-lg hover:bg-s-elevated cursor-default">
                <span className={`h-2 w-2 rounded-full shrink-0 ${isRecent(p.timestamp) ? "bg-s-success" : "bg-s-muted"}`} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-s-text truncate">{p.person_id}</p>
                  <p className={`text-[10px] font-mono ${ROLE_COLOUR[p.person_type] ?? "text-s-muted"}`}>
                    {p.person_type.toUpperCase()}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* System status */}
      <div className="p-3 border-t border-s-border">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-s-success shrink-0" />
          {!collapsed && <span className="font-mono text-[10px] text-s-muted tracking-widest">OPERATIONAL</span>}
        </div>
      </div>
    </aside>
  );
}
