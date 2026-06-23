"use client";
import { useEffect, useRef, useState } from "react";
import { ref, onValue } from "firebase/database";
import { db } from "@/config/firebase";

export interface BeaconScanRecord {
  uuid: string;
  major: string;
  minor: string;
  rssi: number;
  ap_mac: string;
  last_seen: number;   // Unix seconds — matches AP heartbeat convention
  registered: boolean;
}

/**
 * Subscribe to /beacon_scans in RTDB. Returns the raw scan records keyed by
 * "uuid_major_minor" (RTDB node format).
 *
 * Consumers compute online/offline themselves from `last_seen` (10 s threshold).
 * A 1 s ticker forces consumer re-renders so a beacon going silent — which
 * never emits a new RTDB event — still flips to "offline" on time.
 */
export function useBeaconScans(): Record<string, BeaconScanRecord> {
  const rawRef = useRef<Record<string, BeaconScanRecord>>({});
  const [scans, setScans] = useState<Record<string, BeaconScanRecord>>({});

  useEffect(() => {
    const r = ref(db, "/beacon_scans");
    const unsub = onValue(r, (snap) => {
      const data = (snap.val() ?? {}) as Record<string, BeaconScanRecord>;
      rawRef.current = data;
      setScans(data);
    });

    const interval = setInterval(() => {
      setScans({ ...rawRef.current });
    }, 1_000);

    return () => {
      unsub();
      clearInterval(interval);
    };
  }, []);

  return scans;
}
