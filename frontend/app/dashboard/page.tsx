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
      <FloorMapArea />

      <section>
        <h2 className="font-mono text-xs text-s-muted tracking-widest uppercase mb-3">
          Active Alerts ({activeAlerts.length})
        </h2>
        <AlertList
          alerts={activeAlerts}
          selectedId={null}
          onSelectAlert={(a) => router.push(`/dashboard/alerts?id=${a.alert_id}`)}
        />
      </section>
    </div>
  );
}
