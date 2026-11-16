"use client";
import { useEffect, useState } from "react";
import { apStatus, useAPHeartbeats } from "@/hooks/useAPHeartbeats";
import { cctvStatus, useCCTVHeartbeats } from "@/hooks/useCCTVHeartbeats";
import { subscribeToAPs, subscribeToCCTVs, type APRecord, type CCTVRecord } from "@/services/floorService";

interface Props {
  buildingId: string | null;
  floorId: string | null;
}

export default function DeviceStatusPanel({ buildingId, floorId }: Props) {
  const [aps, setAps] = useState<APRecord[]>([]);
  const [cctvs, setCctvs] = useState<CCTVRecord[]>([]);
  const { heartbeats: apHeartbeats, loaded: apHeartbeatsLoaded } = useAPHeartbeats();
  const { heartbeats: cctvHeartbeats, loaded: cctvHeartbeatsLoaded } = useCCTVHeartbeats();

  useEffect(() => {
    if (!buildingId || !floorId) { setAps([]); setCctvs([]); return; }
    const unsubAPs = subscribeToAPs(buildingId, floorId, setAps);
    const unsubCCTVs = subscribeToCCTVs(buildingId, floorId, setCctvs);
    return () => { unsubAPs(); unsubCCTVs(); };
  }, [buildingId, floorId]);

  if (!buildingId || !floorId || (aps.length === 0 && cctvs.length === 0)) return null;

  return (
    <div className="device-status-panel">
      <h3 className="device-status-title">Device Status</h3>

      {aps.length > 0 && (
        <div className="device-status-section">
          <span className="device-status-label">ACCESS POINTS</span>
          {aps.map((ap) => {
            // The same rule as every AP icon (Prompt 142, D2): grey only until
            // the first heartbeat snapshot, then no heartbeat reads as offline.
            const status = apStatus(apHeartbeats, apHeartbeatsLoaded, ap.mac);
            return (
              <div key={ap.id} className="device-status-row">
                <span className={`device-status-dot ${status}`} />
                <span className="device-status-name">{ap.name}</span>
                <span className="device-status-mac">{ap.mac}</span>
                <span className={`device-status-badge ${status}`}>
                  {status === "online" ? "Online" : status === "offline" ? "Offline" : "Unknown"}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {cctvs.length > 0 && (
        <div className="device-status-section">
          <span className="device-status-label">CAMERAS</span>
          {cctvs.map((cctv) => {
            const mac = (cctv.device_mac ?? cctv.mac)?.toUpperCase();
            // The same rule as every camera icon, taken from the APs (Prompt 142, D2):
            // grey only until the first heartbeat snapshot or with no MAC, then no
            // heartbeat reads as offline.
            const status = cctvStatus(cctvHeartbeats, cctvHeartbeatsLoaded, mac);
            const badgeText = !mac ? "No MAC" : status === "online" ? "Online" : status === "offline" ? "Offline" : "Unknown";
            return (
              <div key={cctv.id} className="device-status-row">
                <span className={`device-status-dot ${status}`} />
                <span className="device-status-name">{cctv.name}</span>
                <span className="device-status-mac">{mac ?? "—"}</span>
                <span className={`device-status-badge ${status}`}>{badgeText}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
