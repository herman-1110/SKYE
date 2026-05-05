import type { AlertType } from "@/types/alert";

const CONFIG: Record<AlertType, { bg: string; text: string; label: string }> = {
  man_down:         { bg: "bg-s-danger",   text: "text-white",     label: "MAN DOWN" },
  collision:        { bg: "bg-s-danger",   text: "text-white",     label: "COLLISION" },
  ghost_patrol:     { bg: "bg-s-accent",   text: "text-s-base",    label: "GHOST PATROL" },
  patrol_violation: { bg: "bg-orange-600", text: "text-white",     label: "PATROL BREACH" },
};

export default function AlertTypeBadge({ type }: { type: AlertType }) {
  const c = CONFIG[type] ?? { bg: "bg-s-elevated", text: "text-s-text", label: type.toUpperCase() };
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-semibold tracking-widest ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}
