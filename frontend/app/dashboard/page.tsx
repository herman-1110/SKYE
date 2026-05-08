"use client";
import StatsRow from "@/components/dashboard/StatsRow";
import FloorMapArea from "@/components/dashboard/FloorMapArea";
import AlertList from "@/components/alerts/AlertList";
import { useDashboardStore } from "@/store/dashboardStore";
import { useRouter } from "next/navigation";
import type { AlertRecord } from "@/types/alert";

export default function DashboardPage() {
  const alerts = useDashboardStore((s) => s.alerts);
  const router = useRouter();
  const alertList = Object.values(alerts) as AlertRecord[];
  const activeAlerts = alertList.filter((a) => !a.resolved);

  return (
    <div className="space-y-4 max-w-[1600px]">
      <StatsRow />

      <div className="grid grid-cols-12 gap-4 items-start">
        {/* Map — 8 cols */}
        <div className="col-span-12 lg:col-span-8">
          <FloorMapArea />
        </div>

        {/* Alerts panel — 4 cols */}
        <div className="col-span-12 lg:col-span-4 bento-card flex flex-col gap-3" style={{ minHeight: 320 }}>
          <h2 className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
            Active Alerts ({activeAlerts.length})
          </h2>
          <AlertList
            alerts={activeAlerts}
            selectedId={null}
            onSelectAlert={(a) => router.push(`/dashboard/alerts?id=${a.alert_id}`)}
          />
        </div>
      </div>
    </div>
  );
}
