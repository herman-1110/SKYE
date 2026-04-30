"use client";
import { useState } from "react";
import { useAlerts } from "@/hooks/useAlerts";
import AlertList from "@/components/alerts/AlertList";
import FeedbackForm from "@/components/alerts/FeedbackForm";
import LoadingSpinner from "@/components/shared/LoadingSpinner";
import type { AlertRecord } from "@/types/alert";

export default function AlertsPage() {
  const { alerts, isLoading } = useAlerts();
  const [selected, setSelected] = useState<AlertRecord | null>(null);

  if (isLoading) return <LoadingSpinner />;

  return (
    <main className="p-4 max-w-7xl mx-auto">
      <h1 className="text-xl font-bold mb-4">Alert Management</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <section>
          <AlertList alerts={Object.values(alerts)} onSelectAlert={setSelected} />
        </section>
        <section>
          {selected ? (
            <div className="bg-white rounded-xl shadow p-4">
              <h2 className="font-semibold mb-3">
                Feedback — {selected.alert_type}
              </h2>
              <FeedbackForm
                alert={selected}
                onSubmitted={() => setSelected(null)}
              />
            </div>
          ) : (
            <p className="text-sm text-gray-500">Select an alert to provide feedback.</p>
          )}
        </section>
      </div>
    </main>
  );
}
