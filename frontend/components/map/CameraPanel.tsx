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
import CameraLiveView from "./CameraLiveView";

// Prompt 131 T9: opened by clicking a camera marker on the floor map. Status
// comes from the /cctv_heartbeats subscription (useCCTVHeartbeats, passed in);
// recent events come from the backend's in-memory 15-minute buffer. Prompt 132
// added the live video at the top (CameraLiveView).

const POLL_MS = 3_000;
const EVENTS_SHOWN = 200;        // rows rendered in the scrolling events list
const LIVE_ONLINE_MS = 10_000;   // as useCCTVHeartbeats' ONLINE_THRESHOLD_MS and the backend's live-view check

const PROBE_TEXT: Record<string, string> = {
  ok: "Camera API reachable and the login works",
  auth_error: "Camera login failed. Fix VIGI_CAMERA_PASSWORD in backend/.env; saving the file allows one new attempt",
  no_credentials: "No camera password set (VIGI_CAMERA_PASSWORD), so health checks are off",
  unreachable: "Camera API not reachable",
  error: "Camera API answered with an error",
};

// "Alarm setup" from what actually arrives. The camera's API can't read its
// Alarm Server settings (Prompt 131 D3), but last_event_at proves them: the
// backend only writes it for an alarm from this camera's MAC, posted from its
// registered IP to the secret alarm path. An empty scene sends nothing, so an
// old last alarm is only a hint, never "broken".
const ALARM_RECENT_S = 24 * 3600;
const CHECK_ALARM_SERVER = "check Settings > Event > Alarm Server on the camera";

function alarmSetup(heartbeat: CCTVHeartbeat | undefined, nowMs: number): { text: string; color?: string } {
  if (heartbeat?.alarmConfig === "mismatch") {
    return { text: "Human detection is switched off on the camera, so no People events will arrive", color: "var(--warning, #f59e0b)" };
  }
  const last = heartbeat?.lastEventAt;
  if (last && nowMs / 1000 - last < ALARM_RECENT_S) {
    return { text: `Working: the camera's alarms are reaching SKYE (last one ${ago(last, nowMs)})`, color: "var(--success, #22c55e)" };
  }
  if (last) {
    return { text: `Last alarm ${ago(last, nowMs)}. If people have been in view since, ${CHECK_ALARM_SERVER}` };
  }
  return { text: `No alarm received yet. If people have been in view, ${CHECK_ALARM_SERVER}` };
}

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

  // Live view needs the camera's RTSP port reachable - the backend's own check.
  // Not `status`, which also stays "unknown" until the first OpenAPI probe.
  const reachable = !!heartbeat?.lastSeen && nowMs - heartbeat.lastSeen * 1000 < LIVE_ONLINE_MS;
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

        {/* Live video (Prompt 132): admins only; closes with the panel */}
        <div className="px-5 pt-4">
          <CameraLiveView buildingId={buildingId} cctv={cctv} online={reachable} />
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
            {(() => {
              const setup = alarmSetup(heartbeat, nowMs);
              return <span style={setup.color ? { color: setup.color } : undefined}>{setup.text}</span>;
            })()}
          </Row>
          <Row label="Checkpoint">{checkpoint ? checkpoint.name : cctv.checkpoint_ap_id ? "(AP no longer on this floor)" : "None"}</Row>
          <Row label="MAC / IP">
            <span className="font-mono">{cctv.device_mac ?? cctv.mac ?? "-"}</span>
            <span className="text-s-muted"> · </span>
            <span className="font-mono">{cctv.ip ?? "no IP set"}</span>
          </Row>
          {heartbeat?.ipMismatch && heartbeat.ipMismatch !== cctv.ip && (
            <Row label="IP warning">
              <span style={{ color: "var(--warning, #f59e0b)" }}>
                Found at {heartbeat.ipMismatch}, but alarms are only accepted from {cctv.ip ?? "its registered IP"}.
                Use &quot;Use the new IP&quot; in the floor plan&apos;s device editor.
              </span>
            </Row>
          )}
        </div>

        <div className="px-5 pb-5">
          <div className="flex items-baseline gap-2 mb-2">
            <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Recent events</span>
            <span className="font-mono text-[10px] text-s-muted">
              {data && data.detections.length > 0 ? `${data.detections.length} · ` : ""}last 15 min · updates every 3 s
            </span>
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
            // Scrolls inside a fixed height (about 10 rows), newest first, with
            // the header kept in view.
            <div className="max-h-64 overflow-y-auto rounded-lg border border-s-border/60">
              <table className="w-full text-xs">
                <thead className="sticky top-0" style={{ background: "var(--bg-surface)" }}>
                  <tr className="border-b border-s-border">
                    {["Time", "Event", "People"].map((h) => (
                      <th key={h} className="font-mono text-[10px] text-s-muted tracking-widest uppercase text-left py-1.5 px-3">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.detections.slice(0, EVENTS_SHOWN).map((d, i) => (
                    <tr key={`${d.received_at}-${i}`} className="border-b border-s-border/40 last:border-0">
                      <td className="py-1 px-3 font-mono text-[11px] text-s-muted">{clock(d.received_at)}</td>
                      <td className="py-1 px-3" style={{ color: d.is_human ? "var(--success, #22c55e)" : "var(--text-secondary)" }}>
                        {eventLabel(d.event_type)}
                      </td>
                      <td className="py-1 px-3 font-mono text-[11px] text-s-text">{d.is_human ? (d.obj_num ?? "-") : "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.detections.length > EVENTS_SHOWN && (
                <p className="font-mono text-[10px] text-s-muted text-center py-2">
                  Showing the latest {EVENTS_SHOWN} of {data.detections.length}
                </p>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>,
    document.body,
  );
}
