"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getMyAlerts } from "@/services/guardService";
import AlertCard from "@/components/alerts/AlertCard";
import type { AlertRecord } from "@/types/alert";

export default function GuardAlertsPage() {
  const { user } = useAuth();
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    user.getIdToken().then(async (token) => {
      const data = await getMyAlerts(token);
      setAlerts(data);
      setLoading(false);
    });
  }, [user]);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <span className="h-6 w-6 rounded-full border-2 border-s-accent border-t-transparent animate-spin" />
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">
        My Alerts ({alerts.length})
      </h1>
      {alerts.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-48 gap-2 bg-s-surface border border-s-border rounded-lg">
          <p className="text-s-muted text-sm">No alerts for your account.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <AlertCard
              key={alert.alert_id}
              alert={alert}
              selected={false}
              onClick={() => {}}
            />
          ))}
        </div>
      )}
    </div>
  );
}
