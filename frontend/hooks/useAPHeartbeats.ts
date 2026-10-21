"use client";
import { useEffect, useRef, useState } from "react";
import { ref, onValue } from "firebase/database";
import { db } from "@/config/firebase";

const ONLINE_THRESHOLD_MS = 10_000;

export type APStatus = "online" | "offline" | "unknown";

export interface APHeartbeat {
  mac: string;
  name: string;
  status: APStatus;
}

/** Every /ap_heartbeats node by MAC (upper case), with its status, and
 *  whether the first snapshot has arrived yet. */
export function useAPHeartbeats(): { heartbeats: Record<string, APHeartbeat>; loaded: boolean } {
  const rawRef = useRef<Record<string, { name: string; last_seen: number }>>({});
  const [heartbeats, setHeartbeats] = useState<Record<string, APHeartbeat>>({});
  const [loaded, setLoaded] = useState(false);

  const recompute = () => {
    const now = Date.now();
    const result: Record<string, APHeartbeat> = {};
    for (const [mac, { name, last_seen }] of Object.entries(rawRef.current)) {
      const age = now - last_seen * 1000;
      result[mac] = {
        mac,
        name,
        status: age < ONLINE_THRESHOLD_MS ? "online" : "offline",
      };
    }
    setHeartbeats(result);
  };

  useEffect(() => {
    const r = ref(db, "/ap_heartbeats");
    const unsub = onValue(r, (snap) => {
      const data = snap.val() ?? {};
      const raw: Record<string, { name: string; last_seen: number }> = {};
      for (const entry of Object.values(data) as Partial<{ mac: string; name: string; last_seen: number }>[]) {
        // Skip malformed/legacy nodes (e.g. missing mac) instead of throwing and
        // silently killing the update for every other AP in this snapshot.
        if (typeof entry?.mac !== "string" || typeof entry.last_seen !== "number") continue;
        raw[entry.mac.toUpperCase()] = { name: entry.name ?? "", last_seen: entry.last_seen };
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

/** One rule for every AP icon and status dot (Prompt 142, D2): online while
 *  its heartbeat is under 10 s old, offline when older or missing, and
 *  "unknown" (grey) only until the first snapshot has arrived, so a page load
 *  never flashes red. */
export function apStatus(heartbeats: Record<string, APHeartbeat>, loaded: boolean, mac: string): APStatus {
  if (!loaded) return "unknown";
  return heartbeats[mac.toUpperCase()]?.status === "online" ? "online" : "offline";
}
