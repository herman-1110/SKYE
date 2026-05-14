"use client";
import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { FloorRecord } from "@/types/floor";
import {
  listAPs, createAP, deleteAP,
  listCCTVs, createCCTV, deleteCCTV,
  type APRecord, type CCTVRecord,
} from "@/services/floorService";
import { toast } from "@/store/toastStore";

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
  const [cctvName, setCctvName] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [hoveredMarker, setHoveredMarker] = useState<{ label: string; x: number; y: number } | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    listAPs(buildingId, floor.id).then(setAps).catch(() => {});
    listCCTVs(buildingId, floor.id).then(setCctvs).catch(() => {});
  }, [buildingId, floor.id]);

  const handleMapClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!placementMode || !imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setPendingPct({ x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)) });
  };

  const handleSaveAP = async () => {
    if (!pendingPct) return;
    setSaving(true);
    try {
      const ap = await createAP(buildingId, floor.id, {
        name: apName.trim() || "AP",
        mac: apMac.trim(),
        x_pct: pendingPct.x,
        y_pct: pendingPct.y,
      });
      setAps((prev) => [...prev, ap]);
      toast.success(`AP "${ap.name}" placed`);
      setPendingPct(null); setApName(""); setApMac(""); setPlacementMode(null);
    } catch { toast.error("Failed to place AP"); }
    finally { setSaving(false); }
  };

  const handleSaveCCTV = async () => {
    if (!pendingPct) return;
    setSaving(true);
    try {
      const cctv = await createCCTV(buildingId, floor.id, {
        name: cctvName.trim() || "CCTV",
        x_pct: pendingPct.x,
        y_pct: pendingPct.y,
      });
      setCctvs((prev) => [...prev, cctv]);
      toast.success(`CCTV "${cctv.name}" placed`);
      setPendingPct(null); setCctvName(""); setPlacementMode(null);
    } catch { toast.error("Failed to place CCTV"); }
    finally { setSaving(false); }
  };

  const handleDeleteAP = async (id: string) => {
    setDeletingId(id);
    try { await deleteAP(buildingId, floor.id, id); setAps((p) => p.filter((a) => a.id !== id)); toast.success("AP removed"); }
    catch { toast.error("Failed to remove AP"); }
    finally { setDeletingId(null); }
  };

  const handleDeleteCCTV = async (id: string) => {
    setDeletingId(id);
    try { await deleteCCTV(buildingId, floor.id, id); setCctvs((p) => p.filter((c) => c.id !== id)); toast.success("CCTV removed"); }
    catch { toast.error("Failed to remove CCTV"); }
    finally { setDeletingId(null); }
  };

  const cancelPlacement = () => {
    setPendingPct(null); setPlacementMode(null); setApName(""); setApMac(""); setCctvName("");
  };

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase mr-1">Devices</span>
        <button
          onClick={() => setPlacementMode(placementMode === "ap" ? null : "ap")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${placementMode === "ap" ? "bg-s-accent text-s-base" : "bg-s-elevated border border-s-border text-s-muted hover:text-s-text"}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>
          </svg>
          {placementMode === "ap" ? "Cancel" : "Add AP"}
        </button>
        <button
          onClick={() => setPlacementMode(placementMode === "cctv" ? null : "cctv")}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${placementMode === "cctv" ? "bg-s-accent text-s-base" : "bg-s-elevated border border-s-border text-s-muted hover:text-s-text"}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
          </svg>
          {placementMode === "cctv" ? "Cancel" : "Add CCTV"}
        </button>
        {placementMode && (
          <span className="font-mono text-[10px] text-s-accent">Click on the map to place</span>
        )}
        {onClose && (
          <button onClick={onClose} className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-s-elevated border border-s-border text-xs font-mono text-s-muted hover:text-s-danger transition-colors">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            Close
          </button>
        )}
      </div>

      {/* Map canvas */}
      <div
        className="relative w-full rounded-xl overflow-hidden border border-s-border bg-s-elevated select-none"
        style={{ cursor: placementMode ? "crosshair" : "default" }}
        onClick={handleMapClick}
      >
        <img
          ref={imgRef}
          src={floor.url}
          alt={floor.name}
          className="w-full h-auto pointer-events-none"
          draggable={false}
        />

        {/* AP markers */}
        {aps.map((ap) => (
          <div
            key={ap.id}
            className="group absolute"
            style={{ left: `${ap.x_pct * 100}%`, top: `${ap.y_pct * 100}%`, transform: "translate(-50%, -50%)", pointerEvents: "auto", zIndex: 10 }}
            onMouseEnter={(e) => setHoveredMarker({ label: ap.name, x: e.clientX, y: e.clientY })}
            onMouseMove={(e) => setHoveredMarker({ label: ap.name, x: e.clientX, y: e.clientY })}
            onMouseLeave={() => setHoveredMarker(null)}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>
            </svg>
            <button
              onClick={(e) => { e.stopPropagation(); handleDeleteAP(ap.id); }}
              disabled={deletingId === ap.id}
              className="absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full bg-s-danger text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center disabled:opacity-40"
              style={{ fontSize: 8 }}
            >✕</button>
          </div>
        ))}

        {/* CCTV markers */}
        {cctvs.map((cctv) => (
          <div
            key={cctv.id}
            className="group absolute"
            style={{ left: `${cctv.x_pct * 100}%`, top: `${cctv.y_pct * 100}%`, transform: "translate(-50%, -50%)", pointerEvents: "auto", zIndex: 10 }}
            onMouseEnter={(e) => setHoveredMarker({ label: cctv.name, x: e.clientX, y: e.clientY })}
            onMouseMove={(e) => setHoveredMarker({ label: cctv.name, x: e.clientX, y: e.clientY })}
            onMouseLeave={() => setHoveredMarker(null)}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
            </svg>
            <button
              onClick={(e) => { e.stopPropagation(); handleDeleteCCTV(cctv.id); }}
              disabled={deletingId === cctv.id}
              className="absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full bg-s-danger text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center disabled:opacity-40"
              style={{ fontSize: 8 }}
            >✕</button>
          </div>
        ))}

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
              {aps.map((ap) => (
                <tr key={ap.id} className="border-b border-s-border/50 last:border-0 hover:bg-s-elevated transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/>
                      </svg>
                      <span className="text-s-text font-medium">{ap.name}</span>
                      {ap.mac && <span className="font-mono text-[10px] text-s-muted">{ap.mac}</span>}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[10px] text-s-muted">Access Point</td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => handleDeleteAP(ap.id)} disabled={deletingId === ap.id} className="text-s-muted hover:text-s-danger transition-colors disabled:opacity-40">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                    </button>
                  </td>
                </tr>
              ))}
              {cctvs.map((cctv) => (
                <tr key={cctv.id} className="border-b border-s-border/50 last:border-0 hover:bg-s-elevated transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                      </svg>
                      <span className="text-s-text font-medium">{cctv.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[10px] text-s-muted">CCTV Camera</td>
                  <td className="px-4 py-2.5 text-right">
                    <button onClick={() => handleDeleteCCTV(cctv.id)} disabled={deletingId === cctv.id} className="text-s-muted hover:text-s-danger transition-colors disabled:opacity-40">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                    </button>
                  </td>
                </tr>
              ))}
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
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">MAC Address</label>
                <input type="text" placeholder="e.g. CC:BA:BD:81:9D:CD" value={apMac} onChange={(e) => setApMac(e.target.value)} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text font-mono placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
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

      {/* CCTV placement modal */}
      {pendingPct && placementMode === "cctv" && typeof document !== "undefined" && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={cancelPlacement}>
          <div className="w-full max-w-xs rounded-xl overflow-hidden" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }} onClick={(e) => e.stopPropagation()}>
            <div className="px-5 py-4 border-b border-s-border">
              <h3 className="font-mono text-xs text-s-muted tracking-widest uppercase">Place CCTV Camera</h3>
            </div>
            <div className="px-5 py-4 space-y-3">
              <div className="space-y-1">
                <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Camera Name</label>
                <input autoFocus type="text" placeholder="e.g. VIGI-C540" value={cctvName} onChange={(e) => setCctvName(e.target.value)} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
              </div>
            </div>
            <div className="flex gap-2 px-5 py-4 border-t border-s-border">
              <button onClick={cancelPlacement} className="px-4 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors">Cancel</button>
              <button onClick={handleSaveCCTV} disabled={saving} className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
                {saving && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
                {saving ? "Placing…" : "Place CCTV"}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
