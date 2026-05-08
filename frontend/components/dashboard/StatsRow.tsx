"use client";
import { useDashboardStore } from "@/store/dashboardStore";
import type { AlertRecord } from "@/types/alert";

interface StatCardProps {
  label: string;
  value: string | number;
  pulse?: boolean;
}

function StatCard({ label, value, pulse }: StatCardProps) {
  return (
    <div className="bento-card rounded-2xl flex flex-col gap-2">
      <span className="text-[11px] font-mono text-s-muted tracking-widest uppercase">{label}</span>
      <span className={`font-mono text-4xl font-bold leading-none ${pulse ? "text-s-accent animate-amber-pulse" : "text-s-text"}`}>
        {value}
      </span>
    </div>
  );
}

export default function StatsRow() {
  const positions = useDashboardStore((s) => s.positions);
  const alerts    = useDashboardStore((s) => s.alerts);

  const alertList    = Object.values(alerts) as AlertRecord[];
  const activeAlerts = alertList.filter((a) => !a.resolved).length;
  const ghostPatrols = alertList.filter((a) => a.alert_type === "ghost_patrol").length;
  const personnel    = Object.keys(positions).length;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatCard label="Active Personnel"      value={personnel} />
      <StatCard label="Active Alerts"         value={activeAlerts} pulse={activeAlerts > 0} />
      <StatCard label="Patrol Compliance"     value="—" />
      <StatCard label="Ghost Patrol Detected" value={ghostPatrols} />
    </div>
  );
}
