import type { CSSProperties } from "react";
import type { APStatus } from "@/hooks/useAPHeartbeats";

// The one AP glyph, used wherever an access point is drawn: a dot with radio
// waves either side, on the same 24x24 grid as the camera icon (the ring
// overflows it on purpose). Stroke and the centre dot follow currentColor, so
// callers set the colour with `color`: apStatusColor() for a placed AP
// (Prompt 142, D2).
export default function ApIcon({ size = 14, className, style }: {
  size?: number;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} style={style}
         aria-hidden="true">
      <circle cx="12" cy="12" r="13" />
      <circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none" />
      <path d="M7.5 9.2a4 4 0 0 0 0 5.6" />
      <path d="M5 7a7.5 7.5 0 0 0 0 10" />
      <path d="M16.5 9.2a4 4 0 0 1 0 5.6" />
      <path d="M19 7a7.5 7.5 0 0 1 0 10" />
    </svg>
  );
}

/** Green online, red offline, grey until the first heartbeat snapshot (see apStatus). */
export function apStatusColor(status: APStatus): string {
  return status === "online" ? "var(--success, #22c55e)"
    : status === "offline" ? "var(--danger, #ef4444)"
    : "var(--text-secondary)";
}
