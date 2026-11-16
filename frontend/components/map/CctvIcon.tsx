import type { CSSProperties } from "react";
import type { CCTVStatus } from "@/hooks/useCCTVHeartbeats";
import { apStatusColor } from "./ApIcon";

// The one CCTV glyph, used wherever a camera is drawn: a bullet camera tilted
// down on a wall bracket, on the same 24x24 grid as the AP icon and kept
// inside it. Stroke and the LED dot follow currentColor, so callers set the
// colour with `color`: cctvStatusColor() for a placed camera.
export default function CctvIcon({ size = 14, className, style }: {
  size?: number;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className={className} style={style} aria-hidden="true">
      <g transform="rotate(20 10 9)">
        <rect x="3" y="5" width="13" height="7" rx="2" />
        <path d="M16 7.25 21 5.5v7l-5-1.75" />
        <circle cx="6.5" cy="8.5" r="1" fill="currentColor" stroke="none" />
      </g>
      <path d="M7 11.5V15a2 2 0 0 1-2 2H3" />
      <path d="M3 14.5v5" />
    </svg>
  );
}

/** The same colours as the AP icons: green online, red offline, grey unknown (see cctvStatus). */
export function cctvStatusColor(status: CCTVStatus): string {
  return apStatusColor(status);
}

// A camera on a floor plan: the glyph in a round chip with a coloured ring, so
// it stays readable on any floor-plan image. `color` is the status, so it has
// no default.
export function CctvMarker({ color, size = 26 }: {
  color: string;
  size?: number;
}) {
  return (
    <span
      style={{
        width: size, height: size, borderRadius: "50%",
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "var(--bg-surface)", border: `1.5px solid ${color}`, color,
        boxShadow: "0 1px 4px rgba(0,0,0,0.35)",
      }}
    >
      <CctvIcon size={Math.round(size * 0.65)} />
    </span>
  );
}
