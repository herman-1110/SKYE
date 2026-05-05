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
    <div className="bg-s-surface border border-s-border rounded-lg p-4 flex flex-col gap-1">
      <span className="text-[10px] font-mono text-s-muted tracking-widest uppercase">{label}</span>
      <span className={`font-mono text-3xl font-semibold ${pulse ? "text-s-accent animate-amber-pulse" : "text-s-text"}`}>
        {value}
      </span>
    </div>
  );
}

export default function StatsRow() {
  const positions = useDashboardStore((s) => s.positions);
  const alerts    = useDashboardStore((s) => s.alerts);

  const alertList = Object.values(alerts) as AlertRecord[];
  const activeAlerts  = alertList.filter((a) => !a.resolved).length;
  const ghostPatrols  = alertList.filter((a) => a.alert_type === "ghost_patrol").length;
  const personnel     = Object.keys(positions).length;

  return (
    <div className="grid grid-cols-4 gap-3">
      <StatCard label="Active Personnel"       value={personnel} />
      <StatCard label="Active Alerts"          value={activeAlerts} pulse={activeAlerts > 0} />
      <StatCard label="Patrol Compliance"      value="—" />
      <StatCard label="Ghost Patrol Detected"  value={ghostPatrols} />
    </div>
  );
}
