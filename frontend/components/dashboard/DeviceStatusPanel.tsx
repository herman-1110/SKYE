"use client";
import { useEffect, useState } from "react";
import { useAPHeartbeats } from "@/hooks/useAPHeartbeats";
import { useCCTVHeartbeats } from "@/hooks/useCCTVHeartbeats";
import { subscribeToAPs, subscribeToCCTVs, type APRecord, type CCTVRecord } from "@/services/floorService";

interface Props {
  buildingId: string | null;
  floorId: string | null;
}

export default function DeviceStatusPanel({ buildingId, floorId }: Props) {
  const [aps, setAps] = useState<APRecord[]>([]);
  const [cctvs, setCctvs] = useState<CCTVRecord[]>([]);
  const apStatuses = useAPHeartbeats();
  const cctvStatuses = useCCTVHeartbeats();

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
            const status = apStatuses[ap.mac.toUpperCase()]?.status ?? "offline";
            return (
              <div key={ap.id} className="device-status-row">
                <span className={`device-status-dot ${status}`} />
                <span className="device-status-name">{ap.name}</span>
                <span className="device-status-mac">{ap.mac}</span>
                <span className={`device-status-badge ${status}`}>
                  {status === "online" ? "Online" : "Offline"}
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
            const hasMac = !!cctv.mac;
            const status = hasMac ? (cctvStatuses[cctv.mac!.toUpperCase()] ?? "offline") : null;
            const badgeClass = hasMac ? (status === "online" ? "online" : "offline") : "unknown";
            return (
              <div key={cctv.id} className="device-status-row">
                <span className={`device-status-dot ${badgeClass}`} />
                <span className="device-status-name">{cctv.name}</span>
                <span className="device-status-mac">{cctv.mac ?? "—"}</span>
                <span className={`device-status-badge ${badgeClass}`}>
                  {hasMac ? (status === "online" ? "Online" : "Offline") : "No MAC"}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
