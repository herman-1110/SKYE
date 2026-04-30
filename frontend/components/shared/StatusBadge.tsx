type Status = "online" | "offline" | "alert";

const STYLES: Record<Status, string> = {
  online:  "bg-green-100 text-green-800",
  offline: "bg-gray-100 text-gray-600",
  alert:   "bg-red-100 text-red-700",
};

const LABELS: Record<Status, string> = {
  online:  "Online",
  offline: "Offline",
  alert:   "Alert",
};

export default function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STYLES[status]}`}>
      {LABELS[status]}
    </span>
  );
}
