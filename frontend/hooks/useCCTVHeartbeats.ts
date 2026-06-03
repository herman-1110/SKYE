"use client";
import { useEffect, useRef, useState } from "react";
import { ref, onValue } from "firebase/database";
import { db } from "@/config/firebase";

const ONLINE_THRESHOLD_MS = 10_000;

export type CCTVStatus = "online" | "offline" | "unknown";

export function useCCTVHeartbeats(): Record<string, CCTVStatus> {
  const rawRef = useRef<Record<string, number>>({});
  const [statuses, setStatuses] = useState<Record<string, CCTVStatus>>({});

  const recompute = () => {
    const now = Date.now();
    const result: Record<string, CCTVStatus> = {};
    for (const [mac, last_seen] of Object.entries(rawRef.current)) {
      const age = now - last_seen * 1000;
      result[mac] = age < ONLINE_THRESHOLD_MS ? "online" : "offline";
    }
    setStatuses(result);
  };

  useEffect(() => {
    const r = ref(db, "/cctv_heartbeats");
    const unsub = onValue(r, (snap) => {
      const data = snap.val() ?? {};
      const raw: Record<string, number> = {};
      for (const entry of Object.values(data) as { mac: string; last_seen: number }[]) {
        raw[entry.mac.toUpperCase()] = entry.last_seen;
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

  return statuses;
}
