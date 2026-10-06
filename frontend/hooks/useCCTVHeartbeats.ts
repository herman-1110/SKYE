"use client";
import { useEffect, useRef, useState } from "react";
import { ref, onValue } from "firebase/database";
import { db } from "@/config/firebase";

// Kept at 10 s (Herman's decision 5, 6 Oct): the backend's TCP liveness probe
// writes last_seen every 5 s while a camera is reachable.
const ONLINE_THRESHOLD_MS = 10_000;

export type CCTVStatus = "online" | "offline" | "unknown";

/** One /cctv_heartbeats node as the backend writes it (Prompt 131). The
 *  simulator's nodes only carry mac, last_seen and device_name. */
export interface CCTVHeartbeat {
  mac: string;
  status: CCTVStatus;
  lastSeen: number | null;      // unix s — last successful TCP connect to the camera
  lastEventAt: number | null;   // unix s — last accepted alarm push
  deviceName: string | null;
  probe: string | null;         // "ok" | "auth_error" | "no_credentials" | "unreachable" | "error"; null on simulator nodes
  probeOkAt: number | null;     // unix s — last time probe was "ok"; null until the first one
  alarmConfig: string | null;   // "mismatch" | "unknown"; null until checked
}

type RawNode = Partial<{
  mac: string; last_seen: number; last_event_at: number; device_name: string;
  probe: string; probe_ok_at: number; alarm_config: string;
}>;

const num = (v: unknown) => (typeof v === "number" ? v : null);
const str = (v: unknown) => (typeof v === "string" ? v : null);

/** "unknown" when there's no heartbeat or the backend's health check has never
 *  succeeded for this camera; otherwise online/offline by last_seen. Nodes with
 *  no probe field at all (the simulator's) use the plain last_seen rule. */
export function cctvStatusOf(hb: Omit<CCTVHeartbeat, "status"> | undefined, nowMs: number): CCTVStatus {
  if (!hb) return "unknown";
  if (hb.probe !== null && hb.probeOkAt === null) return "unknown";
  if (hb.lastSeen === null) return "unknown";
  return nowMs - hb.lastSeen * 1000 < ONLINE_THRESHOLD_MS ? "online" : "offline";
}

/** Heartbeats keyed by upper-case colon MAC ("98:BA:5F:8B:10:03"). A camera
 *  with no entry here has no heartbeat: treat it as "unknown". */
export function useCCTVHeartbeats(): Record<string, CCTVHeartbeat> {
  const rawRef = useRef<Record<string, Omit<CCTVHeartbeat, "status">>>({});
  const [heartbeats, setHeartbeats] = useState<Record<string, CCTVHeartbeat>>({});

  const recompute = () => {
    const now = Date.now();
    const result: Record<string, CCTVHeartbeat> = {};
    for (const [mac, hb] of Object.entries(rawRef.current)) {
      result[mac] = { ...hb, status: cctvStatusOf(hb, now) };
    }
    setHeartbeats(result);
  };

  useEffect(() => {
    const r = ref(db, "/cctv_heartbeats");
    const unsub = onValue(r, (snap) => {
      const data = snap.val() ?? {};
      const raw: Record<string, Omit<CCTVHeartbeat, "status">> = {};
      for (const entry of Object.values(data) as RawNode[]) {
        // Skip malformed/legacy nodes (e.g. missing mac) instead of throwing and
        // silently killing the update for every other CCTV in this snapshot.
        if (typeof entry?.mac !== "string") continue;
        const mac = entry.mac.toUpperCase();
        raw[mac] = {
          mac,
          lastSeen: num(entry.last_seen),
          lastEventAt: num(entry.last_event_at),
          deviceName: str(entry.device_name),
          probe: str(entry.probe),
          probeOkAt: num(entry.probe_ok_at),
          alarmConfig: str(entry.alarm_config),
        };
      }
      rawRef.current = raw;
      recompute();
    });

    const interval = setInterval(recompute, 1_000);

    return () => {
      unsub();
      clearInterval(interval);
    };
  }, []);

  return heartbeats;
}
