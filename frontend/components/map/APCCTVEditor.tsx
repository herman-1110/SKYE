"use client";
import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { FloorRecord } from "@/types/floor";
import {
  subscribeToAPs, createAP, deleteAP, updateAPPosition,
  subscribeToCCTVs, createCCTV, deleteCCTV, updateCCTV, updateCCTVPosition, discoverCameras,
  type APRecord, type CCTVRecord,
} from "@/services/floorService";
import { toast } from "@/store/toastStore";
import { useAPHeartbeats, type APStatus } from "@/hooks/useAPHeartbeats";
import { useCCTVHeartbeats } from "@/hooks/useCCTVHeartbeats";
import MacAddressInput from "@/components/shared/MacAddressInput";
import { isCompleteMac, isValidMac } from "@/utils/macUtils";

const IPV4_REGEX = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;

function StatusDot({ status }: { status: APStatus }) {
  const color =
    status === "online"  ? "var(--success, #22c55e)" :
    status === "offline" ? "var(--danger,  #ef4444)" :
                           "var(--text-secondary)";
  return (
    <span
      style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: color, flexShrink: 0 }}
      title={status}
    />
  );
}

type PlacementMode = "ap" | "cctv" | null;

interface Props {
  buildingId: string;
  floor: FloorRecord;
  onClose?: () => void;
}

export default function APCCTVEditor({ buildingId, floor, onClose }: Props) {
  const [aps, setAps] = useState<APRecord[]>([]);
  const [cctvs, setCctvs] = useState<CCTVRecord[]>([]);
  const [placementMode, setPlacementMode] = useState<PlacementMode>(null);
  const [pendingPct, setPendingPct] = useState<{ x: number; y: number } | null>(null);
  const [apName, setApName] = useState("");
  const [apMac, setApMac] = useState("");
  const [macError, setMacError] = useState("");
  const [cctvName, setCctvName] = useState("");
  const [cctvMac, setCctvMac] = useState("");
  const [cctvMacError, setCctvMacError] = useState("");
  // Prompt 131: camera IP (alarms are only accepted from it), the checkpoint
  // (AP) it covers, and edit mode for an existing camera.
  const [cctvIp, setCctvIp] = useState("");
  const [cctvIpError, setCctvIpError] = useState("");
  const [cctvCheckpoint, setCctvCheckpoint] = useState("");
  const [cctvFormError, setCctvFormError] = useState("");
  const [editingCctvId, setEditingCctvId] = useState<string | null>(null);
  const apHeartbeats = useAPHeartbeats();
  const cctvHeartbeats = useCCTVHeartbeats();

  const placedMacs = new Set(aps.map((a) => a.mac.toUpperCase()));
  const unregisteredOnlineAPs = Object.values(apHeartbeats)
    .filter((hb) => hb.status === "online" && !placedMacs.has(hb.mac.toUpperCase()))
    .map((hb) => ({ mac: hb.mac, name: hb.name }));

  // Prompt 131b: cameras the backend found (ONVIF discovery or an alarm push)
  // that aren't on this floor — the camera twin of the AP list above. A node
  // with a probe field belongs to a camera registered somewhere (only
  // registered cameras get OpenAPI checks), so it's left out: tighter than
  // the AP list, which shows other floors' APs until the create 409s.
  // Listed while online, or found by a scan in the last 10 minutes.
  const placedCamMacs = new Set(cctvs.map((c) => (c.device_mac ?? c.mac ?? "").toUpperCase()).filter(Boolean));
  const nowS = Math.floor(Date.now() / 1000);
  const unplacedCameras = Object.values(cctvHeartbeats)
    .filter((hb) => hb.discoveredVia && hb.probe === null && !placedCamMacs.has(hb.mac)
      && (hb.status === "online" || (hb.discoveredAt !== null && nowS - hb.discoveredAt < 600)))
    .sort((a, b) => a.mac.localeCompare(b.mac));
  const [scanning, setScanning] = useState(false);
  const [fixingIpId, setFixingIpId] = useState<string | null>(null);

  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [hoveredMarker, setHoveredMarker] = useState<{ label: string; x: number; y: number } | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  // Drag-to-reposition an already-placed device. dragPct overlays the live
  // pointer position on top of whatever's in Firestore; the underlying
  // aps/cctvs arrays are never optimistically mutated, so if the PATCH on
  // release fails, clearing dragPct alone puts the marker right back where
  // it started — no separate revert logic needed.
  const [dragTarget, setDragTarget] = useState<{ type: "ap" | "cctv"; id: string } | null>(null);
  const [dragPct, setDragPct] = useState<{ x: number; y: number } | null>(null);
  const dragPctRef = useRef<{ x: number; y: number } | null>(null);
  // Grab origin, in both cursor and marker-pct space — lets handleMove apply
  // the cursor's DELTA rather than snapping the marker's center to wherever
  // the cursor currently is. Without this, an off-center grab (you rarely
  // click the exact pixel-center of a 22px icon) makes the marker visibly
  // jump to re-center under the cursor the instant you move it.
  const dragOriginRef = useRef<{ clientX: number; clientY: number; xPct: number; yPct: number } | null>(null);

  useEffect(() => {
    const unsubAPs = subscribeToAPs(buildingId, floor.id, setAps);
    const unsubCCTVs = subscribeToCCTVs(buildingId, floor.id, setCctvs);
    return () => { unsubAPs(); unsubCCTVs(); };
  }, [buildingId, floor.id]);

  const handleMarkerPointerDown =
    (type: "ap" | "cctv", id: string, xPct: number, yPct: number) => (e: React.PointerEvent) => {
      if ((e.target as HTMLElement).closest("button")) return;
      if (placementMode || dragTarget) return;
      e.preventDefault();
      e.stopPropagation();
      dragOriginRef.current = { clientX: e.clientX, clientY: e.clientY, xPct, yPct };
      dragPctRef.current = { x: xPct, y: yPct };
      setDragTarget({ type, id });
      setDragPct({ x: xPct, y: yPct });
    };

  useEffect(() => {
    if (!dragTarget) return;

    const handleMove = (e: PointerEvent) => {
      if (!imgRef.current || !dragOriginRef.current) return;
      const rect = imgRef.current.getBoundingClientRect();
      const origin = dragOriginRef.current;
      const dxPct = (e.clientX - origin.clientX) / rect.width;
      const dyPct = (e.clientY - origin.clientY) / rect.height;
      const x = Math.max(0, Math.min(1, origin.xPct + dxPct));
      const y = Math.max(0, Math.min(1, origin.yPct + dyPct));
      dragPctRef.current = { x, y };
      setDragPct({ x, y });
    };

    const handleUp = async () => {
      const final = dragPctRef.current;
      const target = dragTarget;
      dragOriginRef.current = null;
      if (!final) { setDragTarget(null); setDragPct(null); return; }

      // Deliberately keep rendering from dragPct (the exact drop point) until
      // the PATCH resolves — clearing it immediately made the marker jump
      // back to its stale pre-drag position for the round-trip, then jump
      // forward again once Firestore's onSnapshot caught up. x_m/y_m are no
      // longer computed here — the backend derives them from x_pct/y_pct +
      // the floor's calibrated scale (see floorService.ts).
      try {
        if (target.type === "ap") {
          await updateAPPosition(buildingId, floor.id, target.id, { x_pct: final.x, y_pct: final.y });
        } else {
          await updateCCTVPosition(buildingId, floor.id, target.id, { x_pct: final.x, y_pct: final.y });
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "";
        toast.error(msg.toLowerCase().includes("not calibrated") ? msg : "Failed to update device position");
      } finally {
        setDragTarget(null);
        setDragPct(null);
      }
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    window.addEventListener("pointercancel", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      window.removeEventListener("pointercancel", handleUp);
    };
  }, [dragTarget]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleMapClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!placementMode || !imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setPendingPct({ x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) });
  };

  const handleSaveAP = async () => {
    if (!pendingPct) return;
    if (!isCompleteMac(apMac)) { setMacError("Please complete all 6 MAC address segments"); return; }
    if (!isValidMac(apMac))    { setMacError("Invalid MAC address format"); return; }
    setMacError("");
    setSaving(true);
    // x_m/y_m are no longer computed here — the backend derives them from
    // x_pct/y_pct + the floor's calibrated scale (see floorService.ts). The
    // "Add AP" button is disabled on an uncalibrated floor, so the 409 below
    // is a defensive path (direct API call), not something normal use hits.
    try {
      const ap = await createAP(buildingId, floor.id, {
        name: apName.trim() || "AP",
        mac: apMac,
        x_pct: pendingPct.x,
        y_pct: pendingPct.y,
      });
      toast.success(`AP "${ap.name}" placed`);
      setPendingPct(null); setApName(""); setApMac(""); setPlacementMode(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("409") || msg.toLowerCase().includes("already exists")) {
        if (msg.toLowerCase().includes("another floor")) {
          setMacError("This MAC is already registered on a different floor. Each AP must have a unique MAC across all floors.");
        } else {
          setMacError("An AP with this MAC already exists on this floor.");
        }
      } else if (msg.toLowerCase().includes("not calibrated")) {
        toast.error(msg);
      } else {
        toast.error("Failed to place AP");
      }
    }
    finally { setSaving(false); }
  };

  const resetCctvForm = () => {
    setCctvName(""); setCctvMac(""); setCctvMacError(""); setCctvIp(""); setCctvIpError("");
    setCctvCheckpoint(""); setCctvFormError(""); setEditingCctvId(null);
  };

  const openEditCCTV = (cctv: CCTVRecord) => {
    setPendingPct(null); setPlacementMode(null);
    setCctvName(cctv.name);
    setCctvMac((cctv.device_mac ?? cctv.mac ?? "").toUpperCase());
    setCctvIp(cctv.ip ?? "");
    setCctvCheckpoint(cctv.checkpoint_ap_id ?? "");
    setCctvMacError(""); setCctvIpError(""); setCctvFormError("");
    setEditingCctvId(cctv.id);
  };

  const handleSaveCCTV = async () => {
    if (!pendingPct && !editingCctvId) return;
    // MAC and IP are needed for alarms to be accepted; the checkpoint is optional.
    if (!isCompleteMac(cctvMac)) { setCctvMacError("Please complete all 6 MAC address segments"); return; }
    if (!isValidMac(cctvMac))    { setCctvMacError("Invalid MAC address format"); return; }
    if (!IPV4_REGEX.test(cctvIp.trim())) { setCctvIpError("Enter the camera's IPv4 address, e.g. 192.168.0.101"); return; }
    setCctvMacError(""); setCctvIpError(""); setCctvFormError("");
    setSaving(true);
    const fields = {
      name: cctvName.trim() || "CCTV",
      mac: cctvMac,
      ip: cctvIp.trim(),
      checkpoint_ap_id: cctvCheckpoint || null,
    };
    try {
      if (editingCctvId) {
        const cctv = await updateCCTV(buildingId, floor.id, editingCctvId, fields);
        toast.success(`Camera "${cctv.name}" updated`);
      } else if (pendingPct) {
        const cctv = await createCCTV(buildingId, floor.id, { ...fields, x_pct: pendingPct.x, y_pct: pendingPct.y });
        toast.success(`Camera "${cctv.name}" placed`);
        setPendingPct(null); setPlacementMode(null);
      }
      resetCctvForm();
    } catch (err: unknown) {
      // 409 (MAC already registered) and 422 (bad MAC / IP / checkpoint) come
      // back from the backend as one plain sentence — show it as it is.
      const msg = err instanceof Error && err.message ? err.message : "";
      setCctvFormError(msg || (editingCctvId ? "Failed to update the camera" : "Failed to place the camera"));
    }
    finally { setSaving(false); }
  };

  const handleDeleteAP = async (id: string) => {
    setDeletingId(id);
    setHoveredMarker(null);
    try { await deleteAP(buildingId, floor.id, id); toast.success("AP removed"); }
    catch { toast.error("Failed to remove AP"); }
    finally { setDeletingId(null); }
  };

  const handleDeleteCCTV = async (id: string) => {
    setDeletingId(id);
    setHoveredMarker(null);
    try { await deleteCCTV(buildingId, floor.id, id); toast.success("CCTV removed"); }
    catch { toast.error("Failed to remove CCTV"); }
    finally { setDeletingId(null); }
  };

  const cancelPlacement = () => {
    setPendingPct(null); setPlacementMode(null); setApName(""); setApMac(""); setMacError(""); resetCctvForm();
  };

  const scanForCameras = async () => {
    setScanning(true);
    try {
      const { found } = await discoverCameras();
      const fresh = found.filter((c) => !c.registered).length;
      toast.success(found.length === 0
        ? "Scan finished: no cameras found on this network"
        : `Scan finished: ${found.length} camera${found.length > 1 ? "s" : ""} found` + (fresh ? `, ${fresh} not on any floor yet` : ""));
    } catch (err: unknown) {
      toast.error(err instanceof Error && err.message ? `Scan failed: ${err.message}` : "Scan failed");
    } finally { setScanning(false); }
  };

  // Click a discovered camera: start placement with its name, MAC and IP
  // filled in; clicking the map opens the usual dialog to pick the checkpoint and save.
  const startPlacingDetectedCamera = (mac: string, name: string | null, ip: string | null) => {
    resetCctvForm();
    setCctvMac(mac.toUpperCase());
    setCctvName(name ?? "");
    setCctvIp(ip ?? "");
    setPendingPct(null);
    setPlacementMode("cctv");
    toast.info(`Click on the map to place ${name || mac}`);
  };

  const applyDiscoveredIp = async (cctv: CCTVRecord, ip: string) => {
    setFixingIpId(cctv.id);
    try {
      await updateCCTV(buildingId, floor.id, cctv.id, { ip });
      toast.success(`${cctv.name} now accepts alarms from ${ip}`);
    } catch (err: unknown) {
      toast.error(err instanceof Error && err.message ? err.message : "Failed to update the camera's IP");
    } finally { setFixingIpId(null); }
  };

  const startPlacingDetectedAP = (mac: string, name = "") => {
    setApMac(mac);
    setApName(name);
    setMacError("");
    setPlacementMode("ap");
    toast.info(`Click on the map to place ${name || mac}`);
  };

  return (
    <div className="space-y-4">
      {/* Calibration guard */}
      {!floor.scale_pixels_per_meter && (
        <div className="calibration-warning">
          ⚠ This floor is not calibrated. Calibrate before placing APs or CCTVs.
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase mr-1">Devices</span>
        <button
          onClick={() => setPlacementMode(placementMode === "ap" ? null : "ap")}
          disabled={!floor.scale_pixels_per_meter}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${placementMode === "ap" ? "bg-s-accent text-s-base" : "bg-s-elevated border border-s-border text-s-muted hover:text-s-text"}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="13"/><circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/><path d="M7.5 9.2a4 4 0 0 0 0 5.6"/><path d="M5 7a7.5 7.5 0 0 0 0 10"/><path d="M16.5 9.2a4 4 0 0 1 0 5.6"/><path d="M19 7a7.5 7.5 0 0 1 0 10"/>
          </svg>
          {placementMode === "ap" ? "Cancel" : "Add AP"}
        </button>
        <button
          onClick={() => setPlacementMode(placementMode === "cctv" ? null : "cctv")}
          disabled={!floor.scale_pixels_per_meter}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${placementMode === "cctv" ? "bg-s-accent text-s-base" : "bg-s-elevated border border-s-border text-s-muted hover:text-s-text"}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 8 Q4 4 8 4 L22 4 Q28 6 28 10 Q28 14 22 16 L8 16 Q4 16 4 12 Z"/><ellipse cx="5.5" cy="10" rx="3.5" ry="4.5"/><circle cx="5.5" cy="10" r="1.5" fill="var(--danger)" stroke="none"/><path d="M20 16 L19 20 L15 20"/><rect x="13" y="19" width="4" height="6" rx="1"/><rect x="17" y="20" width="5" height="8" rx="1"/>
          </svg>
          {placementMode === "cctv" ? "Cancel" : "Add CCTV"}
        </button>
        {placementMode && (
          <span className="font-mono text-[10px] text-s-accent">Click on the map to place</span>
        )}
        {onClose && (
          <button onClick={onClose} className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-s-elevated border border-s-border text-xs font-mono text-s-muted hover:text-s-danger transition-colors">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            Close
          </button>
        )}
      </div>

      {/* Detected-but-unplaced APs panel */}
      {floor.scale_pixels_per_meter && unregisteredOnlineAPs.length > 0 && (
        <div className="bento-card p-3 border border-s-accent/40">
          <div className="flex items-center gap-2 mb-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-s-accent opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-s-accent" />
            </span>
            <span className="font-mono text-[10px] text-s-accent tracking-widest uppercase">
              {unregisteredOnlineAPs.length} AP{unregisteredOnlineAPs.length > 1 ? "s" : ""} online but not placed
            </span>
          </div>
          <p className="font-mono text-[10px] text-s-muted mb-2.5 leading-relaxed">
            These access points are sending data but aren&apos;t on this floor yet. Click one to place it.
          </p>
          <div className="flex flex-col gap-1.5">
            {unregisteredOnlineAPs.map((ap) => (
              <button
                key={ap.mac}
                onClick={() => startPlacingDetectedAP(ap.mac, ap.name)}
                className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-s-elevated border border-s-border hover:border-s-accent transition-colors text-left group"
              >
                <div className="flex items-center gap-2">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="13"/><circle cx="12" cy="12" r="2.2" fill="var(--accent)" stroke="none"/><path d="M7.5 9.2a4 4 0 0 0 0 5.6"/><path d="M5 7a7.5 7.5 0 0 0 0 10"/><path d="M16.5 9.2a4 4 0 0 1 0 5.6"/><path d="M19 7a7.5 7.5 0 0 1 0 10"/>
                  </svg>
                  <div className="flex flex-col leading-tight">
                    {ap.name && <span className="font-mono text-[11px] text-s-text">{ap.name}</span>}
                    <span className="font-mono text-[10px] text-s-muted">{ap.mac}</span>
                  </div>
                </div>
                <span className="flex items-center gap-1.5 font-mono text-[10px] text-s-accent opacity-0 group-hover:opacity-100 transition-opacity">
                  Place
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Online cameras not on the map (Prompt 131b) — always shown on a
          calibrated floor, so "Scan now" is there even before anything is found */}
      {floor.scale_pixels_per_meter && (
        <div className="bento-card p-3 border border-s-border">
          <div className="flex items-center gap-2 mb-2">
            {unplacedCameras.length > 0 && (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-s-accent opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-s-accent" />
              </span>
            )}
            <span className={`font-mono text-[10px] tracking-widest uppercase ${unplacedCameras.length > 0 ? "text-s-accent" : "text-s-muted"}`}>
              {unplacedCameras.length > 0
                ? `${unplacedCameras.length} camera${unplacedCameras.length > 1 ? "s" : ""} online but not placed`
                : "Cameras not on the map"}
            </span>
            <button
              onClick={scanForCameras}
              disabled={scanning}
              className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-s-elevated border border-s-border text-[10px] font-mono text-s-muted hover:text-s-text transition-colors disabled:opacity-40"
            >
              {scanning && <span className="h-2.5 w-2.5 rounded-full border-2 border-s-muted border-t-transparent animate-spin" />}
              {scanning ? "Scanning…" : "Scan now"}
            </button>
          </div>
          {unplacedCameras.length === 0 ? (
            <p className="font-mono text-[10px] text-s-muted leading-relaxed">
              No cameras found yet. The backend looks for VIGI cameras on this network every minute; Scan now looks straight away.
            </p>
          ) : (
            <>
              <p className="font-mono text-[10px] text-s-muted mb-2.5 leading-relaxed">
                These cameras are on the network but not on this floor yet. Click one to place it.
              </p>
              <div className="flex flex-col gap-1.5">
                {unplacedCameras.map((hb) => (
                  <button
                    key={hb.mac}
                    onClick={() => startPlacingDetectedCamera(hb.mac, hb.deviceName, hb.ip)}
                    className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-s-elevated border border-s-border hover:border-s-accent transition-colors text-left group"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <StatusDot status={hb.status} />
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 8 Q4 4 8 4 L22 4 Q28 6 28 10 Q28 14 22 16 L8 16 Q4 16 4 12 Z"/><ellipse cx="5.5" cy="10" rx="3.5" ry="4.5"/><circle cx="5.5" cy="10" r="1.5" fill="var(--danger)" stroke="none"/><path d="M20 16 L19 20 L15 20"/><rect x="13" y="19" width="4" height="6" rx="1"/><rect x="17" y="20" width="5" height="8" rx="1"/>
                      </svg>
                      <div className="flex flex-col leading-tight min-w-0">
                        <span className="font-mono text-[11px] text-s-text truncate">{hb.deviceName ?? "VIGI camera"}</span>
                        <span className="font-mono text-[10px] text-s-muted">{hb.ip ?? "IP unknown"} · {hb.mac} · {hb.status}</span>
                      </div>
                    </div>
                    <span className="flex items-center gap-1.5 font-mono text-[10px] text-s-accent opacity-0 group-hover:opacity-100 transition-opacity">
                      Place
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Map canvas */}
      <div
        className="relative w-full rounded-xl overflow-hidden border border-s-border bg-s-elevated select-none"
        style={{ cursor: placementMode ? "crosshair" : "default", userSelect: dragTarget ? "none" : undefined }}
        onClick={handleMapClick}
      >
        <img
          ref={imgRef}
          src={floor.url}
          alt={floor.name}
          className="w-full h-auto pointer-events-none"
          draggable={false}
        />

        {/* AP markers — drag an existing one to reposition it */}
        {aps.map((ap) => {
          const isDragging = dragTarget?.type === "ap" && dragTarget.id === ap.id;
          const xPct = isDragging && dragPct ? dragPct.x : ap.x_pct;
          const yPct = isDragging && dragPct ? dragPct.y : ap.y_pct;
          return (
            <div
              key={ap.id}
              className="group absolute"
              style={{
                left: `${xPct * 100}%`, top: `${yPct * 100}%`,
                transform: `translate(-50%, -50%) scale(${isDragging ? 1.15 : 1})`,
                // Only the scale/shadow pop eases in — left/top must stay
                // untransitioned so the marker tracks the cursor instantly.
                transition: "transform 0.12s ease-out, filter 0.12s ease-out",
                pointerEvents: "auto",
                zIndex: isDragging ? 20 : 10,
                cursor: placementMode ? "default" : isDragging ? "grabbing" : "grab",
                filter: isDragging ? "drop-shadow(0 4px 10px rgba(0,0,0,0.45))" : undefined,
                touchAction: "none",
              }}
              onPointerDown={handleMarkerPointerDown("ap", ap.id, ap.x_pct, ap.y_pct)}
              onMouseEnter={(e) => setHoveredMarker({ label: ap.name, x: e.clientX, y: e.clientY })}
              onMouseMove={(e) => setHoveredMarker({ label: ap.name, x: e.clientX, y: e.clientY })}
              onMouseLeave={() => setHoveredMarker(null)}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="13"/><circle cx="12" cy="12" r="2.2" fill="var(--accent)" stroke="none"/><path d="M7.5 9.2a4 4 0 0 0 0 5.6"/><path d="M5 7a7.5 7.5 0 0 0 0 10"/><path d="M16.5 9.2a4 4 0 0 1 0 5.6"/><path d="M19 7a7.5 7.5 0 0 1 0 10"/>
              </svg>
              <button
                onClick={(e) => { e.stopPropagation(); handleDeleteAP(ap.id); }}
                disabled={deletingId === ap.id}
                className="absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full bg-s-danger text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center disabled:opacity-40"
                style={{ fontSize: 8 }}
              >✕</button>
            </div>
          );
        })}

        {/* CCTV markers — drag an existing one to reposition it */}
        {cctvs.map((cctv) => {
          const isDragging = dragTarget?.type === "cctv" && dragTarget.id === cctv.id;
          const xPct = isDragging && dragPct ? dragPct.x : cctv.x_pct;
          const yPct = isDragging && dragPct ? dragPct.y : cctv.y_pct;
          return (
            <div
              key={cctv.id}
              className="group absolute"
              style={{
                left: `${xPct * 100}%`, top: `${yPct * 100}%`,
                transform: `translate(-50%, -50%) scale(${isDragging ? 1.15 : 1})`,
                // Only the scale/shadow pop eases in — left/top must stay
                // untransitioned so the marker tracks the cursor instantly.
                transition: "transform 0.12s ease-out, filter 0.12s ease-out",
                pointerEvents: "auto",
                zIndex: isDragging ? 20 : 10,
                cursor: placementMode ? "default" : isDragging ? "grabbing" : "grab",
                filter: isDragging ? "drop-shadow(0 4px 10px rgba(0,0,0,0.45))" : undefined,
                touchAction: "none",
              }}
              onPointerDown={handleMarkerPointerDown("cctv", cctv.id, cctv.x_pct, cctv.y_pct)}
              onMouseEnter={(e) => setHoveredMarker({ label: cctv.name, x: e.clientX, y: e.clientY })}
              onMouseMove={(e) => setHoveredMarker({ label: cctv.name, x: e.clientX, y: e.clientY })}
              onMouseLeave={() => setHoveredMarker(null)}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 8 Q4 4 8 4 L22 4 Q28 6 28 10 Q28 14 22 16 L8 16 Q4 16 4 12 Z"/><ellipse cx="5.5" cy="10" rx="3.5" ry="4.5"/><circle cx="5.5" cy="10" r="1.5" fill="var(--danger)" stroke="none"/><path d="M20 16 L19 20 L15 20"/><rect x="13" y="19" width="4" height="6" rx="1"/><rect x="17" y="20" width="5" height="8" rx="1"/>
              </svg>
              <button
                onClick={(e) => { e.stopPropagation(); handleDeleteCCTV(cctv.id); }}
                disabled={deletingId === cctv.id}
                className="absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full bg-s-danger text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center disabled:opacity-40"
                style={{ fontSize: 8 }}
              >✕</button>
            </div>
          );
        })}

        {/* Marker tooltip */}
        {hoveredMarker && typeof document !== "undefined" && createPortal(
          <div style={{ position: "fixed", left: hoveredMarker.x + 12, top: hoveredMarker.y - 8, background: "var(--bg-elevated)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "4px 10px", borderRadius: "6px", fontSize: "12px", pointerEvents: "none", zIndex: 9999, fontFamily: "IBM Plex Mono, monospace", whiteSpace: "nowrap" }}>
            {hoveredMarker.label}
          </div>,
          document.body
        )}
      </div>

      {/* Device list */}
      {(aps.length > 0 || cctvs.length > 0) && (
        <div className="bento-card p-0 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-s-border">
                {["Device", "Type", ""].map((h) => (
                  <th key={h} className="font-mono text-[10px] text-s-muted tracking-widest uppercase text-left px-4 py-2.5">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {aps.map((ap) => {
                const status = apHeartbeats[ap.mac.toUpperCase()]?.status ?? "unknown";
                return (
                <tr key={ap.id} className="border-b border-s-border/50 last:border-0 hover:bg-s-elevated transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <StatusDot status={status} />
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="15"/><circle cx="12" cy="12" r="2.2" fill="var(--accent)" stroke="none"/><path d="M7.5 9.2a4 4 0 0 0 0 5.6"/><path d="M5 7a7.5 7.5 0 0 0 0 10"/><path d="M16.5 9.2a4 4 0 0 1 0 5.6"/><path d="M19 7a7.5 7.5 0 0 1 0 10"/>
                      </svg>
                      <span className="text-s-text font-medium">{ap.name}</span>
                      <span className="font-mono text-[10px] text-s-muted">{ap.mac}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[10px] text-s-muted capitalize">{status === "unknown" ? "Access Point" : status}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => handleDeleteAP(ap.id)} disabled={deletingId === ap.id} className="text-s-muted hover:text-s-danger transition-colors disabled:opacity-40">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                    </button>
                  </td>
                </tr>
                );
              })}
              {cctvs.map((cctv) => {
                const mac = (cctv.device_mac ?? cctv.mac)?.toUpperCase();
                const status = mac ? (cctvHeartbeats[mac]?.status ?? "unknown") : "unknown";
                const checkpoint = cctv.checkpoint_ap_id ? aps.find((a) => a.id === cctv.checkpoint_ap_id) : undefined;
                return (
                <tr key={cctv.id} className="border-b border-s-border/50 last:border-0 hover:bg-s-elevated transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <StatusDot status={status} />
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 8 Q4 4 8 4 L22 4 Q28 6 28 10 Q28 14 22 16 L8 16 Q4 16 4 12 Z"/><ellipse cx="5.5" cy="10" rx="3.5" ry="4.5"/><circle cx="5.5" cy="10" r="1.5" fill="var(--danger)" stroke="none"/><path d="M20 16 L19 20 L15 20"/><rect x="13" y="19" width="4" height="6" rx="1"/><rect x="17" y="20" width="5" height="8" rx="1"/>
                      </svg>
                      <span className="text-s-text font-medium">{cctv.name}</span>
                      <span className="font-mono text-[10px] text-s-muted">{mac ?? "no MAC"}</span>
                      {cctv.ip && <span className="font-mono text-[10px] text-s-muted">{cctv.ip}</span>}
                    </div>
                    {checkpoint && (
                      <div className="font-mono text-[10px] text-s-muted mt-0.5 pl-4">covers {checkpoint.name}</div>
                    )}
                    {(() => {
                      // Prompt 131b: discovery found this camera at another IP.
                      const moved = mac ? cctvHeartbeats[mac]?.ipMismatch : null;
                      if (!moved || moved === cctv.ip) return null;
                      return (
                        <div className="flex items-center gap-2 mt-1 pl-4 flex-wrap">
                          <span className="font-mono text-[10px]" style={{ color: "var(--warning, #f59e0b)" }}>
                            ⚠ Found at {moved}, but alarms are only accepted from {cctv.ip ?? "its registered IP"}
                          </span>
                          <button
                            onClick={() => applyDiscoveredIp(cctv, moved)}
                            disabled={fixingIpId === cctv.id}
                            className="px-2 py-0.5 rounded-md border text-[10px] font-mono transition-colors disabled:opacity-40"
                            style={{ borderColor: "var(--warning, #f59e0b)", color: "var(--warning, #f59e0b)" }}
                          >
                            {fixingIpId === cctv.id ? "Saving…" : "Use the new IP"}
                          </button>
                        </div>
                      );
                    })()}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[10px] text-s-muted capitalize">{status === "unknown" ? "CCTV Camera" : status}</td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <button onClick={() => openEditCCTV(cctv)} className="text-s-muted hover:text-s-text transition-colors mr-3" title="Edit camera" aria-label={`Edit ${cctv.name}`}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                    </button>
                    <button onClick={() => handleDeleteCCTV(cctv.id)} disabled={deletingId === cctv.id} className="text-s-muted hover:text-s-danger transition-colors disabled:opacity-40" title="Remove camera" aria-label={`Remove ${cctv.name}`}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                    </button>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {aps.length === 0 && cctvs.length === 0 && (
        <p className="font-mono text-[10px] text-s-muted text-center py-4 tracking-widest">
          No devices placed. Add an AP or CCTV above.
        </p>
      )}

      {/* AP placement modal */}
      {pendingPct && placementMode === "ap" && typeof document !== "undefined" && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={cancelPlacement}>
          <div className="w-full max-w-xs rounded-xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }} onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-s-border">
              <h3 className="font-mono text-xs text-s-muted tracking-widest uppercase">Place Access Point</h3>
            </div>
            <div className="px-5 py-4 space-y-3">
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">AP Name</label>
                <input autoFocus type="text" placeholder="e.g. EAP725-Outdoor" value={apName} onChange={(e) => setApName(e.target.value)} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
              </div>
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                  MAC Address <span className="text-s-danger">*</span>
                </label>
                <MacAddressInput
                  value={apMac}
                  onChange={(mac) => { setApMac(mac); setMacError(""); }}
                  error={macError}
                />
              </div>
            </div>
            <div className="flex gap-2 px-5 py-4 border-t border-s-border">
              <button onClick={cancelPlacement} className="px-4 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors">Cancel</button>
              <button onClick={handleSaveAP} disabled={saving} className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
                {saving && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
                {saving ? "Placing…" : "Place AP"}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* CCTV add / edit modal */}
      {((pendingPct && placementMode === "cctv") || editingCctvId) && typeof document !== "undefined" && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={cancelPlacement}>
          <div className="w-full max-w-sm rounded-xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }} onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-s-border">
              <h3 className="font-mono text-xs text-s-muted tracking-widest uppercase">{editingCctvId ? "Edit CCTV Camera" : "Place CCTV Camera"}</h3>
            </div>
            <div className="px-5 py-4 space-y-3">
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Camera Name</label>
                <input autoFocus type="text" placeholder="e.g. VIGI-C540" value={cctvName} onChange={(e) => setCctvName(e.target.value)} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
              </div>
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                  MAC Address <span className="text-s-danger">*</span>
                </label>
                <MacAddressInput
                  value={cctvMac}
                  onChange={(mac) => { setCctvMac(mac); setCctvMacError(""); setCctvFormError(""); }}
                  error={cctvMacError}
                />
                <p className="font-mono text-[10px] text-s-muted">Paste it with dashes or colons, e.g. 98-BA-5F-8B-10-03</p>
              </div>
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                  IP Address <span className="text-s-danger">*</span>
                </label>
                <input type="text" inputMode="decimal" placeholder="e.g. 192.168.0.101" value={cctvIp}
                  onChange={(e) => { setCctvIp(e.target.value); setCctvIpError(""); setCctvFormError(""); }}
                  className="w-full bg-s-elevated border rounded-lg px-3 py-2 text-sm font-mono text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
                  style={{ borderColor: cctvIpError ? "var(--danger, #ef4444)" : "var(--border)" }} />
                {cctvIpError && <p style={{ color: "var(--danger, #ef4444)", fontSize: 11 }}>{cctvIpError}</p>}
                <p className="font-mono text-[10px] text-s-muted">Alarms are only accepted from this address. Reserve it in the router&apos;s DHCP.</p>
              </div>
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                  Covers Checkpoint <span className="text-s-muted">(optional)</span>
                </label>
                <select value={cctvCheckpoint} onChange={(e) => { setCctvCheckpoint(e.target.value); setCctvFormError(""); }}
                  className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text focus:outline-none focus:border-s-accent transition-colors">
                  <option value="">None</option>
                  {aps.map((ap) => (
                    <option key={ap.id} value={ap.id}>{ap.name} ({ap.mac})</option>
                  ))}
                </select>
              </div>
              {cctvFormError && (
                <p className="text-xs rounded-lg px-3 py-2" style={{ color: "var(--danger, #ef4444)", background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)" }}>
                  {cctvFormError}
                </p>
              )}
            </div>
            <div className="flex gap-2 px-5 py-4 border-t border-s-border">
              <button onClick={cancelPlacement} className="px-4 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors">Cancel</button>
              <button onClick={handleSaveCCTV} disabled={saving} className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
                {saving && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
                {saving ? (editingCctvId ? "Saving…" : "Placing…") : (editingCctvId ? "Save Camera" : "Place CCTV")}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
