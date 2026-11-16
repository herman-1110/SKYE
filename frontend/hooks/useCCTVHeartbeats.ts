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
  status: CCTVStatus;           // this node alone, which may have no last_seen yet. A placed camera's status is cctvStatus()
  lastSeen: number | null;      // unix s — last successful TCP connect to the camera
  lastEventAt: number | null;   // unix s — last accepted alarm push
  deviceName: string | null;
  probe: string | null;         // "ok" | "auth_error" | "no_credentials" | "unreachable" | "error"; null on simulator nodes. Not part of status: CameraPanel shows it, and APCCTVEditor uses it to leave registered cameras out of its list
  alarmConfig: string | null;   // "mismatch" | "unknown"; null until checked
  // Prompt 131b — camera discovery
  ip: string | null;            // where discovery (or an alarm push) last found it
  discoveredVia: string | null; // "onvif", "arp+onvif", "alarm", …; null on nodes discovery never touched
  discoveredAt: number | null;  // unix s
  ipMismatch: string | null;    // registered camera found at this other IP; alarms only come in from the registered one
}

type RawNode = Partial<{
  mac: string; last_seen: number; last_event_at: number; device_name: string;
  probe: string; alarm_config: string;
  ip: string; discovered_via: string; discovered_at: number; ip_mismatch: string;
}>;

const num = (v: unknown) => (typeof v === "number" ? v : null);
const str = (v: unknown) => (typeof v === "string" ? v : null);

/** One node's status, by last_seen alone, as the backend's live-view check does:
 *  "unknown" with no last_seen yet, otherwise online/offline. The OpenAPI probe
 *  doesn't decide it, because that check needs the camera's password. */
function cctvStatusOf(hb: Omit<CCTVHeartbeat, "status">, nowMs: number): CCTVStatus {
  if (hb.lastSeen === null) return "unknown";
  return nowMs - hb.lastSeen * 1000 < ONLINE_THRESHOLD_MS ? "online" : "offline";
}

/** Every /cctv_heartbeats node by upper-case colon MAC ("98:BA:5F:8B:10:03"),
 *  with its status, and whether the first snapshot has arrived yet. */
export function useCCTVHeartbeats(): { heartbeats: Record<string, CCTVHeartbeat>; loaded: boolean } {
  const rawRef = useRef<Record<string, Omit<CCTVHeartbeat, "status">>>({});
  const [heartbeats, setHeartbeats] = useState<Record<string, CCTVHeartbeat>>({});
  const [loaded, setLoaded] = useState(false);

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
          alarmConfig: str(entry.alarm_config),
          ip: str(entry.ip),
          discoveredVia: str(entry.discovered_via),
          discoveredAt: num(entry.discovered_at),
          ipMismatch: str(entry.ip_mismatch),
        };
      }
      rawRef.current = raw;
      recompute();
      setLoaded(true);
    });

    const interval = setInterval(recompute, 1_000);

    return () => {
      unsub();
      clearInterval(interval);
    };
  }, []);

  return { heartbeats, loaded };
}

/** One rule for every camera icon and status, the same as apStatus (Prompt 142,
 *  D2): online while its heartbeat is under 10 s old, offline when older or
 *  missing, and "unknown" (grey) only until the first snapshot has arrived, so a
 *  page load never flashes red, or for a camera with no MAC, which can't have a
 *  heartbeat. */
export function cctvStatus(heartbeats: Record<string, CCTVHeartbeat>, loaded: boolean, mac: string | undefined): CCTVStatus {
  if (!loaded || !mac) return "unknown";
  return heartbeats[mac.toUpperCase()]?.status === "online" ? "online" : "offline";
}
