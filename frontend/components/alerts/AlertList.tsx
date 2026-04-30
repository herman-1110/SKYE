"use client";
import type { AlertRecord } from "@/types/alert";
import AlertCard from "./AlertCard";

interface Props {
  alerts: AlertRecord[];
  onSelectAlert: (alert: AlertRecord) => void;
}

export default function AlertList({ alerts, onSelectAlert }: Props) {
  if (alerts.length === 0) {
    return <p className="text-sm text-gray-500 py-4">No alerts.</p>;
  }

  return (
    <ul className="space-y-2 overflow-y-auto max-h-96">
      {alerts.map((a) => (
        <li key={a.alert_id}>
          <AlertCard alert={a} onClick={() => onSelectAlert(a)} />
        </li>
      ))}
    </ul>
  );
}
