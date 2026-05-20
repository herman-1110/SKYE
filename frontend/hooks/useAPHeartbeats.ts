"use client";
import { useEffect, useState } from "react";
import { ref, onValue } from "firebase/database";
import { db } from "@/config/firebase";

const ONLINE_THRESHOLD_MS = 10_000;

export type APStatus = "online" | "offline" | "unknown";

export function useAPHeartbeats(): Record<string, APStatus> {
  const [statuses, setStatuses] = useState<Record<string, APStatus>>({});

  useEffect(() => {
    const r = ref(db, "/ap_heartbeats");
    const unsub = onValue(r, (snap) => {
      const data = snap.val() ?? {};
      const now = Date.now();
      const result: Record<string, APStatus> = {};
      for (const entry of Object.values(data) as { mac: string; last_seen: number }[]) {
        const age = now - entry.last_seen * 1000;
        result[entry.mac.toUpperCase()] = age < ONLINE_THRESHOLD_MS ? "online" : "offline";
      }
      setStatuses(result);
    });
    return () => unsub();
  }, []);

  return statuses;
}
