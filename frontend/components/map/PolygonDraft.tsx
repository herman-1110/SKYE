"use client";
import { useCallback, useEffect, useState } from "react";

// Drawing an outline point by point, as the zone editor always has: a click
// adds a point, a right-click closes the outline once it has 3, Esc clears the
// points placed so far (and drawing goes on). Shared by zones (ZoneEditor) and
// the room's walls in Manage Devices (WallGuides), so both feel the same (Prompt
// 143, 18 Nov). The callers keep their own coordinates and pass the preview
// fractions of the box it's drawn in.

/** The points placed so far and the cursor, with the zone's Esc. */
export function usePolygonDraft<P>() {
  const [points, setPoints] = useState<P[]>([]);
  const [cursor, setCursor] = useState<P | null>(null);

  // Esc clears the points placed so far; with none placed it does nothing.
  useEffect(() => {
    if (points.length === 0) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setPoints([]); setCursor(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [points.length]);

  const add = useCallback((p: P) => setPoints((prev) => [...prev, p]), []);
  const clear = useCallback(() => { setPoints([]); setCursor(null); }, []);

  /** The right-click: with 3 points or more, hands them over and clears the
   *  draft; otherwise null and nothing changes. */
  const close = (): P[] | null => {
    if (points.length < 3) return null;
    const pts = points;
    setPoints([]);
    setCursor(null);
    return pts;
  };

  return { points, cursor, add, setCursor, close, clear };
}

const pc = (v: number) => `${v * 100}%`;

/** The drawing preview, in fractions of the box: dashed lines between the
 *  points, a faint closing line from the third point on, a dashed line from
 *  the last point to the cursor, and a dot at each point. */
export function PolygonDraftPreview({ points, cursor }: { points: { x: number; y: number }[]; cursor: { x: number; y: number } | null }) {
  if (points.length === 0 && !cursor) return null;
  const last = points[points.length - 1];
  return (
    <>
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", overflow: "visible", pointerEvents: "none" }}>
        {/* Lines between placed points */}
        {points.map((pt, i) => {
          if (i === 0) return null;
          const p1 = points[i - 1];
          return <line key={i} x1={pc(p1.x)} y1={pc(p1.y)} x2={pc(pt.x)} y2={pc(pt.y)} stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="5 3" />;
        })}
        {/* Closing-line ghost (last → first) when 3+ points */}
        {points.length >= 3 && (
          <line x1={pc(last.x)} y1={pc(last.y)} x2={pc(points[0].x)} y2={pc(points[0].y)} stroke="var(--accent)" strokeWidth="1" strokeDasharray="3 5" opacity="0.4" />
        )}
        {/* Live preview line to cursor */}
        {cursor && points.length > 0 && (
          <line x1={pc(last.x)} y1={pc(last.y)} x2={pc(cursor.x)} y2={pc(cursor.y)} stroke="var(--accent)" strokeWidth="1" strokeDasharray="4 4" opacity="0.6" />
        )}
      </svg>
      {/* Point markers (div-based for circular appearance) */}
      {points.map((pt, i) => (
        <div key={i} style={{ position: "absolute", left: pc(pt.x), top: pc(pt.y), width: 8, height: 8, transform: "translate(-50%,-50%)", borderRadius: "50%", backgroundColor: "var(--accent)", border: "1.5px solid white", pointerEvents: "none", zIndex: 10 }} />
      ))}
    </>
  );
}

/** The hint while drawing, by the number of points placed. */
export function polygonDraftHint(count: number): string {
  return count === 0
    ? "Click to place points · Esc to cancel"
    : count < 3
    ? `${count} point${count !== 1 ? "s" : ""} placed — need at least 3`
    : `${count} points — right-click to close · Esc to cancel`;
}

/** The hint's box, at the bottom of the drawing. */
export function PolygonDraftHint({ count }: { count: number }) {
  return (
    <div style={{ position: "absolute", bottom: 12, left: "50%", transform: "translateX(-50%)", backgroundColor: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 12px", fontSize: 11, color: "var(--text-secondary)", pointerEvents: "none", whiteSpace: "nowrap" }}>
      {polygonDraftHint(count)}
    </div>
  );
}
