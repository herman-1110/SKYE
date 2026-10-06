"use client";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  getCCTVDetections,
  type APRecord,
  type CCTVRecord,
  type CameraDetections,
} from "@/services/floorService";
import type { CCTVHeartbeat, CCTVStatus } from "@/hooks/useCCTVHeartbeats";

// Prompt 131 T9: opened by clicking a camera marker on the floor map. Status
// comes from the /cctv_heartbeats subscription (useCCTVHeartbeats, passed in);
// recent events come from the backend's in-memory 15-minute buffer.

const POLL_MS = 3_000;

const PROBE_TEXT: Record<string, string> = {
  ok: "Camera API reachable and the login works",
  auth_error: "Camera login failed. Fix VIGI_CAMERA_PASSWORD in backend/.env; saving the file allows one new attempt",
  no_credentials: "No camera password set (VIGI_CAMERA_PASSWORD), so health checks are off",
  unreachable: "Camera API not reachable",
  error: "Camera API answered with an error",
};

const ALARM_TEXT: Record<string, string> = {
  mismatch: "Human detection is switched off on the camera, so no People events will arrive",
  unknown: "Can't be confirmed through the camera's API. Check Settings > Event > Alarm Server on the camera",
};

const STATUS_COLOR: Record<CCTVStatus, string> = {
  online: "var(--success, #22c55e)",
  offline: "var(--danger, #ef4444)",
  unknown: "var(--text-secondary, #6b7280)",
};

function ago(unixS: number | null | undefined, nowMs: number): string {
  if (!unixS) return "never";
  const s = Math.max(0, Math.round(nowMs / 1000 - unixS));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return `${Math.floor(s / 3600)} h ago`;
}

function clock(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function eventLabel(eventType: string): string {
  if (eventType === "PEOPLE") return "People";
  if (eventType === "MOTION") return "Motion";
  return eventType.charAt(0) + eventType.slice(1).toLowerCase();
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-1.5 border-b border-s-border/50 last:border-0">
      <span className="w-28 shrink-0 font-mono text-[10px] text-s-muted tracking-widest uppercase pt-0.5">{label}</span>
      <span className="text-xs text-s-text min-w-0 break-words">{children}</span>
    </div>
  );
}

interface Props {
  buildingId: string;
  cctv: CCTVRecord;
  aps: APRecord[];
  heartbeat: CCTVHeartbeat | undefined;
  onClose: () => void;
}

export default function CameraPanel({ buildingId, cctv, aps, heartbeat, onClose }: Props) {
  const [data, setData] = useState<CameraDetections | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const status: CCTVStatus = heartbeat?.status ?? "unknown";
  const lastEventAt = heartbeat?.lastEventAt ?? null;
  const checkpoint = cctv.checkpoint_ap_id ? aps.find((a) => a.id === cctv.checkpoint_ap_id) : undefined;

  // Poll every 3 s while open, and fetch at once whenever a new alarm lands
  // (last_event_at arrives over the RTDB subscription within about a second).
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const d = await getCCTVDetections(buildingId, cctv.floor_id, cctv.id);
        if (!cancelled) { setData(d); setLoadError(null); }
      } catch (err: unknown) {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Couldn't load events");
      }
    };
    load();
    const timer = setInterval(load, POLL_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [buildingId, cctv.floor_id, cctv.id, lastEventAt]);

  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 1_000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const startedRecently = data?.process_started_at
    ? nowMs - Date.parse(data.process_started_at) < (data.window_s ?? 900) * 1000
    : false;
  const lastEvent = data?.detections?.[0];

  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        className="h-full w-full max-w-sm overflow-y-auto shadow-2xl"
        style={{ background: "var(--bg-surface)", borderLeft: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}
        aria-label={`Camera ${cctv.name}`}
      >
        <div className="flex items-center gap-2 px-5 py-4 border-b border-s-border">
          <span style={{ width: 9, height: 9, borderRadius: "50%", background: STATUS_COLOR[status], flexShrink: 0 }} />
          <h3 className="text-sm font-semibold text-s-text truncate">{cctv.name}</h3>
          <span className="font-mono text-[10px] tracking-widest uppercase text-s-muted">{status}</span>
          <button onClick={onClose} className="ml-auto text-s-muted hover:text-s-text transition-colors" aria-label="Close">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        {/* Live video: Prompt 132 */}
        <div className="px-5 pt-4">
          <div className="aspect-video w-full rounded-lg flex items-center justify-center text-center px-4"
               style={{ border: "1.5px dashed var(--border)", background: "var(--bg-elevated)" }}>
            <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
              Live video: coming in Prompt 132
            </span>
          </div>
        </div>

        <div className="px-5 py-3">
          <Row label="Status">
            {status === "online" ? "Online" : status === "offline" ? "Offline" : "Unknown (not verified yet)"}
          </Row>
          <Row label="Last seen">{ago(heartbeat?.lastSeen, nowMs)}</Row>
          <Row label="Last event">
            {lastEventAt ? `${ago(lastEventAt, nowMs)}${lastEvent ? ` (${eventLabel(lastEvent.event_type)})` : ""}` : "none yet"}
          </Row>
          <Row label="Health check">
            {heartbeat?.probe ? (PROBE_TEXT[heartbeat.probe] ?? heartbeat.probe) : "Not checked yet"}
          </Row>
          <Row label="Alarm setup">
            {heartbeat?.alarmConfig ? (ALARM_TEXT[heartbeat.alarmConfig] ?? heartbeat.alarmConfig) : "Not checked yet"}
          </Row>
          <Row label="Checkpoint">{checkpoint ? checkpoint.name : cctv.checkpoint_ap_id ? "(AP no longer on this floor)" : "None"}</Row>
          <Row label="MAC / IP">
            <span className="font-mono">{cctv.device_mac ?? cctv.mac ?? "-"}</span>
            <span className="text-s-muted"> · </span>
            <span className="font-mono">{cctv.ip ?? "no IP set"}</span>
          </Row>
        </div>

        <div className="px-5 pb-5">
          <div className="flex items-baseline gap-2 mb-2">
            <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Recent events</span>
            <span className="font-mono text-[10px] text-s-muted">last 15 min · updates every 3 s</span>
          </div>
          {startedRecently && (
            <p className="font-mono text-[10px] text-s-muted mb-2">
              The backend restarted at {clock(data!.process_started_at)}; earlier events aren&apos;t kept.
            </p>
          )}
          {loadError && <p className="text-xs text-s-danger mb-2">{loadError}</p>}
          {data && data.detections.length === 0 && !loadError && (
            <p className="font-mono text-[10px] text-s-muted py-3 text-center">No events in the last 15 minutes</p>
          )}
          {data && data.detections.length > 0 && (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-s-border">
                  {["Time", "Event", "People"].map((h) => (
                    <th key={h} className="font-mono text-[10px] text-s-muted tracking-widest uppercase text-left py-1.5">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.detections.slice(0, 100).map((d, i) => (
                  <tr key={`${d.received_at}-${i}`} className="border-b border-s-border/40 last:border-0">
                    <td className="py-1 font-mono text-[11px] text-s-muted">{clock(d.received_at)}</td>
                    <td className="py-1" style={{ color: d.is_human ? "var(--success, #22c55e)" : "var(--text-secondary)" }}>
                      {eventLabel(d.event_type)}
                    </td>
                    <td className="py-1 font-mono text-[11px] text-s-text">{d.is_human ? (d.obj_num ?? "-") : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </aside>
    </div>,
    document.body,
  );
}
