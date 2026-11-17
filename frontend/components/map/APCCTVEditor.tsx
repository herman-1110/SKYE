"use client";
import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { FloorRecord } from "@/types/floor";
import {
  subscribeToAPs, createAP, deleteAP, updateAP, updateAPPosition,
  subscribeToCCTVs, createCCTV, deleteCCTV, updateCCTV, updateCCTVPosition, discoverCameras, backendSentence,
  type APRecord, type ApiError, type CCTVRecord,
} from "@/services/floorService";
import { toast } from "@/store/toastStore";
import { apStatus, useAPHeartbeats } from "@/hooks/useAPHeartbeats";
import { cctvStatus, useCCTVHeartbeats } from "@/hooks/useCCTVHeartbeats";
import MacAddressInput from "@/components/shared/MacAddressInput";
import ApIcon, { apStatusColor } from "./ApIcon";
import CctvIcon, { CctvMarker, cctvStatusColor } from "./CctvIcon";
import CameraCone, { CameraDirectionFields, useConeRotation } from "./CameraCone";
import {
  PlaceDistanceFields, WALL_STEP_HINT, WallGuidesOverlay, useStoredWallGuides, useWallSetup, type TypedDistances,
} from "./WallGuides";
import { isCompleteMac, isValidMac } from "@/utils/macUtils";
import { distancesM, formatMetres, guideImageSize, parseMetres, pointAtDistances, type Frac, type ImageSize } from "@/utils/wallGuides";
import { parseFacing, parseFov } from "@/utils/cameraFacing";

const IPV4_REGEX = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;

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
  const [editingApId, setEditingApId] = useState<string | null>(null);
  // Prompt 143, D2: which way the camera faces, as typed in its dialog.
  const [cctvFacing, setCctvFacing] = useState("");
  const [cctvFov, setCctvFov] = useState("");
  const [cctvDirectionError, setCctvDirectionError] = useState("");
  const { heartbeats: apHeartbeats, loaded: apHeartbeatsLoaded } = useAPHeartbeats();
  const { heartbeats: cctvHeartbeats, loaded: cctvHeartbeatsLoaded } = useCCTVHeartbeats();

  const placedMacs = new Set(aps.map((a) => a.mac.toUpperCase()));
  const unregisteredOnlineAPs = Object.values(apHeartbeats)
    .filter((hb) => hb.status === "online" && !placedMacs.has(hb.mac.toUpperCase()))
    .map((hb) => ({ mac: hb.mac, name: hb.name, ip: hb.ip }));

  // Prompt 131b: cameras the backend found (ONVIF discovery or an alarm push)
  // that aren't on this floor — the camera twin of the AP list above. A node
  // with a probe field belongs to a camera registered somewhere (only
  // registered cameras get OpenAPI checks), so it's left out: tighter than
  // the AP list, which shows other floors' APs too (an inactive floor may
  // share them, Prompt 142).
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
  // at: the device's place, for the guides' readout (Prompt 143, D1.3).
  const [hoveredMarker, setHoveredMarker] = useState<{ label: string; x: number; y: number; at?: Frac } | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  // Placement guides (Prompt 143, D1): the walls kept for this floor, the
  // three steps that set them, and the cursor while placing. Without walls,
  // none of it shows and the editor works as before (D1.8).
  const [walls, saveWalls, clearWalls] = useStoredWallGuides(floor.id);
  const wallSetup = useWallSetup(saveWalls);
  const [hoverFrac, setHoverFrac] = useState<Frac | null>(null);
  const [naturalSize, setNaturalSize] = useState<ImageSize | null>(null);
  const [typed, setTyped] = useState<TypedDistances | null>(null);
  const guideSize = guideImageSize(floor, naturalSize);
  const pxPerM = floor.scale_pixels_per_meter;
  const guidesOn = !!(walls && guideSize && pxPerM);
  const metresAt = (p: Frac) => (walls && guideSize && pxPerM ? distancesM(walls, p, guideSize, pxPerM) : null);

  // Turning a camera by the handle at its cone's tip saves facing_deg through
  // the update route (Prompt 143, D2.3).
  const rotation = useConeRotation(imgRef, async (id, deg) => {
    try { await updateCCTV(buildingId, floor.id, id, { facing_deg: deg }); }
    catch (err: unknown) { toast.error(backendSentence(err) ?? "Couldn't turn the camera"); }
  });
  useEffect(() => { if (!pendingPct) setTyped(null); }, [pendingPct]);
  useEffect(() => { if (!placementMode) setHoverFrac(null); }, [placementMode]);
  useEffect(() => {
    const img = imgRef.current;   // already loaded from the cache before onLoad was attached
    if (img?.complete && img.naturalWidth) setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight });
  }, [floor.url]);

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

  // The latest Firestore lists, for the remove safeguard below.
  const apsRef = useRef<APRecord[]>([]);
  const cctvsRef = useRef<CCTVRecord[]>([]);
  useEffect(() => { apsRef.current = aps; }, [aps]);
  useEffect(() => { cctvsRef.current = cctvs; }, [cctvs]);

  const handleMarkerPointerDown =
    (type: "ap" | "cctv", id: string, xPct: number, yPct: number) => (e: React.PointerEvent) => {
      if ((e.target as HTMLElement).closest("button")) return;
      if (placementMode || dragTarget || wallSetup.step || rotation.turning) return;
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

  /** A pointer position as a fraction of the image, clamped to it. */
  const fracAt = (e: { clientX: number; clientY: number }): Frac | null => {
    const rect = imgRef.current?.getBoundingClientRect();
    if (!rect || !rect.width || !rect.height) return null;
    return {
      x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)),
    };
  };

  // The walls' three steps take the map's pointer while they run; with walls
  // set, the cursor is followed in Add AP / Add CCTV mode (Prompt 143, D1).
  const handleMapPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    const p = wallSetup.step ? fracAt(e) : null;
    if (p) wallSetup.pointerDown(p, e);
  };
  const handleMapPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (wallSetup.step) { const p = fracAt(e); if (p) wallSetup.pointerMove(p); }
    else if (placementMode && guidesOn && !pendingPct) setHoverFrac(fracAt(e));
  };
  const handleMapPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const rect = imgRef.current?.getBoundingClientRect();
    const p = wallSetup.step === 1 ? fracAt(e) : null;
    if (p && rect) wallSetup.pointerUp(p, { w: 8 / rect.width, h: 8 / rect.height });
  };

  const handleMapClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (wallSetup.step) { const p = fracAt(e); if (p) wallSetup.click(p); return; }
    if (!placementMode || !imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const clicked = { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) };
    setPendingPct(clicked);
    // With walls set, the dialog's X and Y start from the clicked point (D1.6).
    const d = metresAt(clicked);
    setTyped(d ? { x: formatMetres(d.x), y: formatMetres(d.y), xEdited: false, yEdited: false, from: clicked } : null);
  };

  /** A typed X or Y moves the point being placed (D1.6): measured from the
   *  same walls, clamped to the image, and saved like a click. A box that
   *  wasn't typed in keeps the clicked point on its axis; one that doesn't
   *  hold a number yet leaves the point where it is. */
  const typeDistance = (axis: "x" | "y", text: string) => {
    if (!typed || !pendingPct || !walls || !guideSize || !pxPerM) return;
    const next = axis === "x" ? { ...typed, x: text, xEdited: true } : { ...typed, y: text, yEdited: true };
    setTyped(next);
    const xM = parseMetres(next.x), yM = parseMetres(next.y);
    const moved = pointAtDistances(walls, next.from, { x: xM ?? 0, y: yM ?? 0 }, guideSize, pxPerM);
    setPendingPct({
      x: next.xEdited && xM !== null ? moved.x : pendingPct.x,
      y: next.yEdited && yM !== null ? moved.y : pendingPct.y,
    });
  };

  const openEditAP = (ap: APRecord) => {
    setPendingPct(null); setPlacementMode(null); resetCctvForm();
    setApName(ap.name); setApMac(ap.mac); setMacError("");
    setEditingApId(ap.id);
  };

  // Renaming only: the MAC is the AP's identity (a different MAC is a
  // different AP - remove this one and place that one).
  const handleRenameAP = async () => {
    if (!editingApId) return;
    const name = apName.trim();
    if (!name) { setMacError("Give the AP a name"); return; }
    setSaving(true);
    try {
      const ap = await updateAP(buildingId, floor.id, editingApId, { name });
      toast.success(`AP renamed to "${ap.name}"`);
      setEditingApId(null); setApName(""); setApMac(""); setMacError("");
    } catch (err: unknown) {
      setMacError(err instanceof Error && err.message ? err.message : "Failed to rename the AP");
    } finally { setSaving(false); }
  };

  const handleSaveAP = async () => {
    if (editingApId) return handleRenameAP();
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
      if (msg.toLowerCase().includes("not calibrated")) {
        toast.error(msg);
      } else if ((err as ApiError)?.status === 409 && msg) {
        // The backend's sentence as it is: the MAC is already on this floor,
        // or on another active floor (Prompt 142). Other floors may share it.
        setMacError(msg);
      } else {
        toast.error("Failed to place AP");
      }
    }
    finally { setSaving(false); }
  };

  const resetCctvForm = () => {
    setCctvName(""); setCctvMac(""); setCctvMacError(""); setCctvIp(""); setCctvIpError("");
    setCctvCheckpoint(""); setCctvFormError(""); setEditingCctvId(null);
    setCctvFacing(""); setCctvFov(""); setCctvDirectionError("");
  };

  const openEditCCTV = (cctv: CCTVRecord) => {
    setPendingPct(null); setPlacementMode(null); setEditingApId(null);
    setCctvName(cctv.name);
    setCctvMac((cctv.device_mac ?? cctv.mac ?? "").toUpperCase());
    setCctvIp(cctv.ip ?? "");
    setCctvCheckpoint(cctv.checkpoint_ap_id ?? "");
    setCctvFacing(cctv.facing_deg != null ? String(cctv.facing_deg) : "");
    setCctvFov(cctv.facing_deg != null && cctv.fov_deg != null ? String(cctv.fov_deg) : "");
    setCctvMacError(""); setCctvIpError(""); setCctvFormError(""); setCctvDirectionError("");
    setEditingCctvId(cctv.id);
  };

  const handleSaveCCTV = async () => {
    if (!pendingPct && !editingCctvId) return;
    // MAC and IP are needed for alarms to be accepted; the checkpoint is optional.
    if (!isCompleteMac(cctvMac)) { setCctvMacError("Please complete all 6 MAC address segments"); return; }
    if (!isValidMac(cctvMac))    { setCctvMacError("Invalid MAC address format"); return; }
    if (!IPV4_REGEX.test(cctvIp.trim())) { setCctvIpError("Enter the camera's IPv4 address, e.g. 192.168.0.101"); return; }
    const facing = parseFacing(cctvFacing), fov = parseFov(cctvFov);
    if (!facing.ok) { setCctvDirectionError("Facing: degrees from 0 to under 360, or empty"); return; }
    if (!fov.ok && facing.value !== null) { setCctvDirectionError("Field of view: degrees from 10 to 360, or empty for 90"); return; }
    setCctvMacError(""); setCctvIpError(""); setCctvFormError(""); setCctvDirectionError("");
    setSaving(true);
    const fields = {
      name: cctvName.trim() || "CCTV",
      mac: cctvMac,
      ip: cctvIp.trim(),
      checkpoint_ap_id: cctvCheckpoint || null,
      // Facing empty: not set, which clears both on an edit. The field of view goes only with a facing (D2).
      ...(facing.value === null ? { facing_deg: null } : { facing_deg: facing.value, fov_deg: fov.ok ? fov.value : null }),
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

  // A remove call can fail although the item is gone: a proxy error while
  // the backend finished the delete, say. So a failure waits up to 3 s for
  // the item to leave the Firestore list, and reports what happened
  // (Prompt 142, D4).
  const leavesList = async (stillListed: () => boolean): Promise<boolean> => {
    const until = Date.now() + 3_000;
    while (stillListed()) {
      if (Date.now() >= until) return false;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    return true;
  };

  const handleDeleteAP = async (id: string) => {
    setDeletingId(id);
    setHoveredMarker(null);
    try { await deleteAP(buildingId, floor.id, id); toast.success("AP removed"); }
    catch (err: unknown) {
      if (await leavesList(() => apsRef.current.some((a) => a.id === id))) toast.success("AP removed");
      else toast.error(backendSentence(err) ?? "Couldn't remove the AP");
    }
    finally { setDeletingId(null); }
  };

  const handleDeleteCCTV = async (id: string) => {
    setDeletingId(id);
    setHoveredMarker(null);
    try { await deleteCCTV(buildingId, floor.id, id); toast.success("CCTV removed"); }
    catch (err: unknown) {
      if (await leavesList(() => cctvsRef.current.some((c) => c.id === id))) toast.success("CCTV removed");
      else toast.error(backendSentence(err) ?? "Couldn't remove the camera");
    }
    finally { setDeletingId(null); }
  };

  const cancelPlacement = () => {
    setPendingPct(null); setPlacementMode(null); setApName(""); setApMac(""); setMacError(""); setEditingApId(null); resetCctvForm();
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
  // The name starts as its IP, or else its device name (Prompt 143, D4.2); it stays editable.
  const startPlacingDetectedCamera = (mac: string, name: string | null, ip: string | null) => {
    resetCctvForm();
    setCctvMac(mac.toUpperCase());
    setCctvName(ip ?? name ?? "");
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
          onClick={() => { wallSetup.cancel(); setPlacementMode(placementMode === "ap" ? null : "ap"); }}
          disabled={!floor.scale_pixels_per_meter}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${placementMode === "ap" ? "bg-s-accent text-s-base" : "bg-s-elevated border border-s-border text-s-muted hover:text-s-text"}`}
        >
          <ApIcon size={12} />
          {placementMode === "ap" ? "Cancel" : "Add AP"}
        </button>
        <button
          onClick={() => { wallSetup.cancel(); setPlacementMode(placementMode === "cctv" ? null : "cctv"); }}
          disabled={!floor.scale_pixels_per_meter}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${placementMode === "cctv" ? "bg-s-accent text-s-base" : "bg-s-elevated border border-s-border text-s-muted hover:text-s-text"}`}
        >
          <CctvIcon size={14} />
          {placementMode === "cctv" ? "Cancel" : "Add CCTV"}
        </button>
        {/* Placement guides (Prompt 143, D1): pick two walls to measure from, or clear them */}
        <button
          onClick={() => { if (wallSetup.step) { wallSetup.cancel(); return; } cancelPlacement(); wallSetup.start(); }}
          disabled={!floor.scale_pixels_per_meter}
          title={walls ? "Draw the room and pick its walls again" : "Draw the room and pick two walls to measure from"}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${wallSetup.step ? "bg-s-accent text-s-base" : "bg-s-elevated border border-s-border text-s-muted hover:text-s-text"}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18"/><path d="M7 3v4M11 3v2M15 3v4M3 7h4M3 11h2M3 15h4"/></svg>
          {wallSetup.step ? "Cancel" : "Walls"}
        </button>
        {walls && !wallSetup.step && (
          <button onClick={clearWalls} className="px-3 py-1.5 rounded-lg text-xs font-mono bg-s-elevated border border-s-border text-s-muted hover:text-s-danger transition-colors">
            Clear walls
          </button>
        )}
        {wallSetup.step ? (
          <span className="font-mono text-[10px] text-s-accent">{WALL_STEP_HINT[wallSetup.step]}</span>
        ) : placementMode && (
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
                // The name starts as its IP, or else its reported name, or empty for the default "AP" (Prompt 143, D4.2)
                onClick={() => startPlacingDetectedAP(ap.mac, ap.ip || ap.name || "")}
                className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-s-elevated border border-s-border hover:border-s-accent transition-colors text-left group"
              >
                <div className="flex items-center gap-2">
                  {/* Accent, not a status colour: these aren't placed here yet (Prompt 142, D2) */}
                  <ApIcon size={12} style={{ color: "var(--accent)" }} />
                  <div className="flex flex-col leading-tight">
                    {ap.name && <span className="font-mono text-[11px] text-s-text">{ap.name}</span>}
                    <span className="font-mono text-[10px] text-s-muted">{ap.ip ?? "IP unknown"} · {ap.mac}</span>
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
                      {/* Accent, not a status colour, as in the AP list (Prompt 142, D2): these aren't placed here yet.
                          The word below is the node's own, so a camera found a moment ago says unknown, not offline */}
                      <CctvIcon size={14} style={{ color: "var(--accent)" }} />
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
        style={{
          cursor: placementMode || wallSetup.step ? "crosshair" : "default",
          userSelect: dragTarget ? "none" : undefined,
          touchAction: wallSetup.step === 1 ? "none" : undefined,
        }}
        onClick={handleMapClick}
        onPointerDown={handleMapPointerDown}
        onPointerMove={handleMapPointerMove}
        onPointerUp={handleMapPointerUp}
        onPointerLeave={() => setHoverFrac(null)}
      >
        <img
          ref={imgRef}
          src={floor.url}
          alt={floor.name}
          className="w-full h-auto pointer-events-none"
          draggable={false}
          onLoad={(e) => setNaturalSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
        />

        {/* The walls, and the guides to the point being placed, dragged or hovered (Prompt 143, D1.3) */}
        {(() => {
          const point: Frac | null = !guidesOn || wallSetup.step ? null
            : dragTarget && dragPct ? dragPct
              : pendingPct && placementMode ? pendingPct
                : placementMode ? hoverFrac
                  : hoveredMarker?.at ?? null;
          return <WallGuidesOverlay walls={guidesOn ? walls : null} setup={wallSetup} point={point}
            distances={point ? metresAt(point) : null} />;
        })()}

        {/* With walls set, a ghost marker follows the cursor in Add AP / Add CCTV mode and stays
            on the point being placed while its dialog is open */}
        {(() => {
          const at = placementMode && guidesOn ? (pendingPct ?? hoverFrac) : null;
          if (!at) return null;
          return (
            <div className="absolute" style={{ left: `${at.x * 100}%`, top: `${at.y * 100}%`, transform: "translate(-50%, -50%)", pointerEvents: "none", zIndex: 12, opacity: pendingPct ? 0.9 : 0.55 }}>
              {placementMode === "ap" ? <ApIcon size={22} style={{ color: "var(--accent)" }} /> : <CctvMarker color="var(--accent)" />}
            </div>
          );
        })()}

        {/* AP markers, coloured by status (Prompt 142, D2) — drag an existing one to reposition it */}
        {aps.map((ap) => {
          const isDragging = dragTarget?.type === "ap" && dragTarget.id === ap.id;
          const xPct = isDragging && dragPct ? dragPct.x : ap.x_pct;
          const yPct = isDragging && dragPct ? dragPct.y : ap.y_pct;
          const status = apStatus(apHeartbeats, apHeartbeatsLoaded, ap.mac);
          const label = `${ap.name} — ${status}`;
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
                // While the walls' steps run, clicks go to the map, never a marker's ✕.
                pointerEvents: wallSetup.step ? "none" : "auto",
                zIndex: isDragging ? 20 : 10,
                cursor: placementMode ? "default" : isDragging ? "grabbing" : "grab",
                filter: isDragging ? "drop-shadow(0 4px 10px rgba(0,0,0,0.45))" : undefined,
                touchAction: "none",
              }}
              onPointerDown={handleMarkerPointerDown("ap", ap.id, ap.x_pct, ap.y_pct)}
              onMouseEnter={(e) => setHoveredMarker({ label, x: e.clientX, y: e.clientY, at: { x: xPct, y: yPct } })}
              onMouseMove={(e) => setHoveredMarker({ label, x: e.clientX, y: e.clientY, at: { x: xPct, y: yPct } })}
              onMouseLeave={() => setHoveredMarker(null)}
            >
              <ApIcon size={22} style={{ color: apStatusColor(status) }} />
              <button
                onClick={(e) => { e.stopPropagation(); handleDeleteAP(ap.id); }}
                disabled={deletingId === ap.id}
                className="absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full bg-s-danger text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center disabled:opacity-40"
                style={{ fontSize: 8 }}
              >✕</button>
            </div>
          );
        })}

        {/* Which way each camera faces, with a handle at the cone's tip to turn it (Prompt 143, D2.3) */}
        {cctvs.map((cctv) => {
          const facing = rotation.shownFacing(cctv.id) ?? cctv.facing_deg;
          if (facing == null) return null;
          const at = (dragTarget?.type === "cctv" && dragTarget.id === cctv.id && dragPct) || { x: cctv.x_pct, y: cctv.y_pct };
          const status = cctvStatus(cctvHeartbeats, cctvHeartbeatsLoaded, (cctv.device_mac ?? cctv.mac)?.toUpperCase());
          const canTurn = !placementMode && !wallSetup.step && !dragTarget;
          return (
            <CameraCone key={`cone-${cctv.id}`} xPct={at.x} yPct={at.y} facingDeg={facing} fovDeg={cctv.fov_deg}
              color={cctvStatusColor(status)}
              onHandlePointerDown={canTurn ? (e) => rotation.begin(e, cctv.id, at, facing) : undefined} />
          );
        })}

        {/* CCTV markers, coloured by status like the APs (Prompt 142, D2) — drag an existing one to reposition it */}
        {cctvs.map((cctv) => {
          const isDragging = dragTarget?.type === "cctv" && dragTarget.id === cctv.id;
          const xPct = isDragging && dragPct ? dragPct.x : cctv.x_pct;
          const yPct = isDragging && dragPct ? dragPct.y : cctv.y_pct;
          const mac = (cctv.device_mac ?? cctv.mac)?.toUpperCase();
          const status = cctvStatus(cctvHeartbeats, cctvHeartbeatsLoaded, mac);
          const label = mac ? `${cctv.name} — ${status}` : cctv.name;
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
                // While the walls' steps run, clicks go to the map, never a marker's ✕.
                pointerEvents: wallSetup.step ? "none" : "auto",
                zIndex: isDragging ? 20 : 10,
                cursor: placementMode ? "default" : isDragging ? "grabbing" : "grab",
                filter: isDragging ? "drop-shadow(0 4px 10px rgba(0,0,0,0.45))" : undefined,
                touchAction: "none",
              }}
              onPointerDown={handleMarkerPointerDown("cctv", cctv.id, cctv.x_pct, cctv.y_pct)}
              onMouseEnter={(e) => setHoveredMarker({ label, x: e.clientX, y: e.clientY, at: { x: xPct, y: yPct } })}
              onMouseMove={(e) => setHoveredMarker({ label, x: e.clientX, y: e.clientY, at: { x: xPct, y: yPct } })}
              onMouseLeave={() => setHoveredMarker(null)}
            >
              <CctvMarker color={cctvStatusColor(status)} />
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
            {(() => {
              // With walls set, the device's distances from them (Prompt 143, D1.3).
              const d = guidesOn && hoveredMarker.at ? metresAt(hoveredMarker.at) : null;
              return d && <div style={{ color: "var(--text-secondary)", marginTop: 2 }}>X {formatMetres(d.x)} m · Y {formatMetres(d.y)} m</div>;
            })()}
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
                const status = apStatus(apHeartbeats, apHeartbeatsLoaded, ap.mac);
                return (
                <tr key={ap.id} className="border-b border-s-border/50 last:border-0 hover:bg-s-elevated transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      {/* The icon's colour is the status (Prompt 142, D2); the word is in the next column */}
                      <ApIcon size={12} style={{ color: apStatusColor(status) }} />
                      <span className="text-s-text font-medium">{ap.name}</span>
                      <span className="font-mono text-[10px] text-s-muted">{ap.mac}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[10px] text-s-muted capitalize">{status === "unknown" ? "Access Point" : status}</td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    <button onClick={() => openEditAP(ap)} className="text-s-muted hover:text-s-text transition-colors mr-3" title="Rename AP" aria-label={`Rename ${ap.name}`}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>
                    </button>
                    <button onClick={() => handleDeleteAP(ap.id)} disabled={deletingId === ap.id} className="text-s-muted hover:text-s-danger transition-colors disabled:opacity-40" title="Remove AP" aria-label={`Remove ${ap.name}`}>
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" overflow="visible" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                    </button>
                  </td>
                </tr>
                );
              })}
              {cctvs.map((cctv) => {
                const mac = (cctv.device_mac ?? cctv.mac)?.toUpperCase();
                const status = cctvStatus(cctvHeartbeats, cctvHeartbeatsLoaded, mac);
                const checkpoint = cctv.checkpoint_ap_id ? aps.find((a) => a.id === cctv.checkpoint_ap_id) : undefined;
                return (
                <tr key={cctv.id} className="border-b border-s-border/50 last:border-0 hover:bg-s-elevated transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      {/* The icon's colour is the status, as on the AP rows (Prompt 142, D2); the word is in the next column */}
                      <CctvIcon size={14} style={{ color: cctvStatusColor(status) }} />
                      <span className="text-s-text font-medium">{cctv.name}</span>
                      <span className="font-mono text-[10px] text-s-muted">{mac ?? "no MAC"}</span>
                      {cctv.ip && <span className="font-mono text-[10px] text-s-muted">{cctv.ip}</span>}
                    </div>
                    {checkpoint && (
                      <div className="font-mono text-[10px] text-s-muted mt-0.5 pl-[22px]">covers {checkpoint.name}</div>
                    )}
                    {(() => {
                      // Prompt 131b: discovery found this camera at another IP.
                      const moved = mac ? cctvHeartbeats[mac]?.ipMismatch : null;
                      if (!moved || moved === cctv.ip) return null;
                      return (
                        <div className="flex items-center gap-2 mt-1 pl-[22px] flex-wrap">
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

      {/* AP place / rename modal */}
      {((pendingPct && placementMode === "ap") || editingApId) && typeof document !== "undefined" && createPortal(
        // With walls set (typed), a light backdrop with no blur, so the guides to the point stay readable (D1.3)
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 ${typed ? "bg-black/20" : "bg-black/50 backdrop-blur-sm"}`} onClick={cancelPlacement}>
          <div className="w-full max-w-xs rounded-xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }} onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-s-border">
              <h3 className="font-mono text-xs text-s-muted tracking-widest uppercase">{editingApId ? "Rename Access Point" : "Place Access Point"}</h3>
            </div>
            <div className="px-5 py-4 space-y-3">
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">AP Name</label>
                <input autoFocus type="text" placeholder="e.g. EAP725-Outdoor" value={apName}
                  onChange={(e) => { setApName(e.target.value); if (editingApId) setMacError(""); }}
                  onKeyDown={(e) => { if (e.key === "Enter" && editingApId) handleSaveAP(); }}
                  className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
              </div>
              {editingApId ? (
                <div className="space-y-1">
                  <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">MAC Address</label>
                  <p className="font-mono text-xs text-s-text">{apMac}</p>
                  {macError && <p style={{ color: "var(--danger, #ef4444)", fontSize: 11 }}>{macError}</p>}
                </div>
              ) : (
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
              )}
              {typed && pendingPct && !editingApId && (
                <PlaceDistanceFields typed={typed} reads={metresAt(pendingPct)} onType={typeDistance} />
              )}
            </div>
            <div className="flex gap-2 px-5 py-4 border-t border-s-border">
              <button onClick={cancelPlacement} className="px-4 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors">Cancel</button>
              <button onClick={handleSaveAP} disabled={saving} className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
                {saving && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
                {editingApId ? (saving ? "Saving…" : "Save AP") : (saving ? "Placing…" : "Place AP")}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* CCTV add / edit modal */}
      {((pendingPct && placementMode === "cctv") || editingCctvId) && typeof document !== "undefined" && createPortal(
        // With walls set (typed), a light backdrop with no blur, so the guides to the point stay readable (D1.3)
        <div className={`fixed inset-0 z-50 flex items-center justify-center p-4 ${typed ? "bg-black/20" : "bg-black/50 backdrop-blur-sm"}`} onClick={cancelPlacement}>
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
              <CameraDirectionFields facing={cctvFacing} fov={cctvFov} error={cctvDirectionError}
                onFacing={(t) => { setCctvFacing(t); setCctvDirectionError(""); setCctvFormError(""); }}
                onFov={(t) => { setCctvFov(t); setCctvDirectionError(""); setCctvFormError(""); }} />
              {typed && pendingPct && !editingCctvId && (
                <PlaceDistanceFields typed={typed} reads={metresAt(pendingPct)} onType={typeDistance} />
              )}
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
