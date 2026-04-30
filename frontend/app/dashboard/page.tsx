"use client";
import { useState } from "react";
import { usePositions } from "@/hooks/usePositions";
import { useAlerts } from "@/hooks/useAlerts";
import FloorMap from "@/components/map/FloorMap";
import AlertList from "@/components/alerts/AlertList";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import type { AlertRecord } from "@/types/alert";

export default function DashboardPage() {
  const { positions, isLoading: posLoading } = usePositions();
  const { alerts, isLoading: alertLoading } = useAlerts();
  const [_selected, setSelected] = useState<AlertRecord | null>(null);

  if (posLoading || alertLoading) return <LoadingSpinner />;

  const positionList = Object.values(positions);
  const alertList = Object.values(alerts);

  return (
    <main className="p-4 space-y-6 max-w-7xl mx-auto">
      <h1 className="text-xl font-bold">SKYE — Live Floor View</h1>
      <FloorMap positions={positionList} />
      <section>
        <h2 className="font-semibold mb-2">Active Alerts ({alertList.length})</h2>
        <AlertList alerts={alertList} onSelectAlert={setSelected} />
      </section>
    </main>
  );
}
