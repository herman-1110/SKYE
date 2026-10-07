import type { CSSProperties, ReactNode } from "react";

// The one CCTV glyph, used wherever a camera is drawn: a bullet camera tilted
// down on a wall bracket, on the same 24x24 grid as the AP icon and kept
// inside it. Stroke and the LED dot follow currentColor, so callers set the
// colour with `color` (or a text-* class).
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

// A camera on a floor plan: the glyph in a round chip with a coloured ring, so
// it stays readable on any floor-plan image. `badge` sits bottom-right (the
// status dot on the dashboard map).
export function CctvMarker({ color = "var(--danger)", size = 26, badge }: {
  color?: string;
  size?: number;
  badge?: ReactNode;
}) {
  return (
    <span
      style={{
        position: "relative", width: size, height: size, borderRadius: "50%",
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "var(--bg-surface)", border: `1.5px solid ${color}`, color,
        boxShadow: "0 1px 4px rgba(0,0,0,0.35)",
      }}
    >
      <CctvIcon size={Math.round(size * 0.65)} />
      {badge}
    </span>
  );
}
