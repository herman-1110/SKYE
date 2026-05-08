"use client";
import { useRef, useState, useCallback } from "react";
import { useZones } from "@/hooks/useZones";
import { createZone, deleteZone, aiDetectZones } from "@/services/zoneService";
import { toast } from "@/store/toastStore";
import type { FloorRecord } from "@/types/floor";
import type { ZoneRecord } from "@/types/zone";

const COLOR_PRESETS = [
  { label: "High Risk",     value: "#ef444433", swatch: "#ef4444" },
  { label: "Normal",        value: "#3b82f633", swatch: "#3b82f6" },
  { label: "Exit/Corridor", value: "#22c55e33", swatch: "#22c55e" },
  { label: "Storage",       value: "#f59e0b33", swatch: "#f59e0b" },
];

function colorSolid(hex8: string): string { return hex8.slice(0, 7); }

interface NaturalSize { w: number; h: number }
interface DrawRect { x: number; y: number; w: number; h: number }
interface DragState {
  key: string;
  mode: "move" | "resize";
  handle?: string;
  startX: number;
  startY: number;
  origZone: { x_min: number; x_max: number; y_min: number; y_max: number };
}
interface Suggestion extends Omit<ZoneRecord, "id" | "floor_plan_id" | "created_at" | "created_by"> {
  _key: string;
}

const HANDLES = [
  { id: "n",  top: "0%",    left: "50%",  cursor: "n-resize"  },
  { id: "s",  top: "100%",  left: "50%",  cursor: "s-resize"  },
  { id: "e",  top: "50%",   left: "100%", cursor: "e-resize"  },
  { id: "w",  top: "50%",   left: "0%",   cursor: "w-resize"  },
  { id: "ne", top: "0%",    left: "100%", cursor: "ne-resize" },
  { id: "nw", top: "0%",    left: "0%",   cursor: "nw-resize" },
  { id: "se", top: "100%",  left: "100%", cursor: "se-resize" },
  { id: "sw", top: "100%",  left: "0%",   cursor: "sw-resize" },
] as const;

function ZoneForm({ onSave, onCancel, saving }: {
  onSave: (name: string, color: string, isHighRisk: boolean) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState("");
  const [color, setColor] = useState(COLOR_PRESETS[1].value);
  const [isHighRisk, setIsHighRisk] = useState(false);

  return (
    <div className="bento-card space-y-3">
      <p className="font-mono text-[10px] text-s-muted tracking-widest uppercase">New Zone</p>
      <input autoFocus type="text" placeholder='e.g. "Loading Bay"' value={name} onChange={(e) => setName(e.target.value)} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
      <div className="flex gap-2 flex-wrap">
        {COLOR_PRESETS.map((p) => (
          <button key={p.value} onClick={() => { setColor(p.value); setIsHighRisk(p.label === "High Risk"); }} className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs transition-colors border ${color === p.value ? "border-s-accent text-s-text" : "border-s-border text-s-muted hover:text-s-text"}`}>
            <span className="h-2.5 w-2.5 rounded-sm shrink-0" style={{ backgroundColor: p.swatch }} />
            {p.label}
          </button>
        ))}
      </div>
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input type="checkbox" checked={isHighRisk} onChange={(e) => setIsHighRisk(e.target.checked)} className="accent-amber-500" />
        <span className="text-xs text-s-muted">Mark as high-risk zone</span>
      </label>
      <div className="flex gap-2">
        <button onClick={() => name.trim() && onSave(name.trim(), color, isHighRisk)} disabled={saving || !name.trim()} className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
          {saving && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
          {saving ? "Saving…" : "Save Zone"}
        </button>
        <button onClick={onCancel} className="px-4 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors">Cancel</button>
      </div>
    </div>
  );
}

// ─── Main ZoneEditor ──────────────────────────────────────────────────────────
interface Props {
  buildingId: string;
  floor: FloorRecord;
  isAdmin: boolean;
}

export default function ZoneEditor({ buildingId, floor, isAdmin }: Props) {
  const { zones, setZones, isLoading } = useZones(buildingId, floor.id);
  const [showZones, setShowZones]         = useState(true);
  const [drawMode, setDrawMode]           = useState(false);
  const [naturalSize, setNaturalSize]     = useState<NaturalSize | null>(null);
  const [drawRect, setDrawRect]           = useState<DrawRect | null>(null);
  const [pendingMetres, setPendingMetres] = useState<{ x_min: number; x_max: number; y_min: number; y_max: number } | null>(null);
  const [savingZone, setSavingZone]       = useState(false);
  const [deletingId, setDeletingId]       = useState<string | null>(null);
  const [aiLoading, setAiLoading]         = useState(false);

  // Pending AI zones — rendered on canvas, not yet saved
  const [pendingZones, setPendingZones]   = useState<Suggestion[]>([]);
  const [selectedKey, setSelectedKey]     = useState<string | null>(null);
  const [dragState, setDragState]         = useState<DragState | null>(null);
  const [editingNameKey, setEditingNameKey] = useState<string | null>(null);
  const [editingName, setEditingName]     = useState("");
  const [savingPending, setSavingPending] = useState(false);
  const [selectedIds, setSelectedIds]     = useState<Set<string>>(new Set());
  const [deletingSelected, setDeletingSelected] = useState(false);
  const [confirmClearAll, setConfirmClearAll]   = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const dragStart    = useRef<{ x: number; y: number } | null>(null);

  const calibrated  = !!floor.scale_pixels_per_meter;
  const scale       = floor.scale_pixels_per_meter ?? 1;
  const maxW        = naturalSize ? naturalSize.w / scale : 0;
  const maxH        = naturalSize ? naturalSize.h / scale : 0;

  const toMetres = useCallback(
    (px: number, py: number) => {
      if (!naturalSize || !containerRef.current) return { x: 0, y: 0 };
      const displayW = containerRef.current.offsetWidth;
      const ratio    = naturalSize.w / displayW;
      return { x: (px * ratio) / scale, y: (py * ratio) / scale };
    },
    [naturalSize, scale],
  );

  const toPct = (metres: number, axis: "x" | "y") => {
    if (!naturalSize) return 0;
    return ((metres * scale) / (axis === "x" ? naturalSize.w : naturalSize.h)) * 100;
  };

  const getRelativePos = (e: React.MouseEvent) => {
    const rect = containerRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  // ── container cursor during drag ─────────────────────────────────────────
  const containerCursor: string | undefined = dragState
    ? dragState.mode === "move" ? "grabbing"
      : dragState.handle === "n" || dragState.handle === "s" ? "ns-resize"
      : dragState.handle === "e" || dragState.handle === "w" ? "ew-resize"
      : dragState.handle === "ne" || dragState.handle === "sw" ? "nesw-resize"
      : "nwse-resize"
    : drawMode ? "crosshair" : undefined;

  // ── draw handlers ────────────────────────────────────────────────────────
  const handleMouseDown = (e: React.MouseEvent) => {
    if (!drawMode || !calibrated) return;
    e.preventDefault();
    const pos = getRelativePos(e);
    dragStart.current = pos;
    setDrawRect({ x: pos.x, y: pos.y, w: 0, h: 0 });
    setPendingMetres(null);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    // Zone drag / resize
    if (dragState) {
      const pos    = getRelativePos(e);
      const deltaX = pos.x - dragState.startX;
      const deltaY = pos.y - dragState.startY;
      if (!naturalSize || !containerRef.current) return;
      const displayW = containerRef.current.offsetWidth;
      const ratio    = naturalSize.w / displayW;
      const dx = (deltaX * ratio) / scale;
      const dy = (deltaY * ratio) / scale;
      const orig = dragState.origZone;

      setPendingZones((prev) =>
        prev.map((z) => {
          if (z._key !== dragState.key) return z;

          if (dragState.mode === "move") {
            const w  = orig.x_max - orig.x_min;
            const h  = orig.y_max - orig.y_min;
            const nx = Math.max(0, Math.min(orig.x_min + dx, maxW - w));
            const ny = Math.max(0, Math.min(orig.y_min + dy, maxH - h));
            return { ...z, x_min: nx, x_max: nx + w, y_min: ny, y_max: ny + h };
          }

          if (dragState.mode === "resize" && dragState.handle) {
            const hid = dragState.handle;
            let { x_min, x_max, y_min, y_max } = orig;
            if (hid.includes("n")) y_min = Math.max(0,    Math.min(orig.y_min + dy, orig.y_max - 0.5));
            if (hid.includes("s")) y_max = Math.max(orig.y_min + 0.5, Math.min(orig.y_max + dy, maxH));
            if (hid.includes("w")) x_min = Math.max(0,    Math.min(orig.x_min + dx, orig.x_max - 0.5));
            if (hid.includes("e")) x_max = Math.max(orig.x_min + 0.5, Math.min(orig.x_max + dx, maxW));
            return { ...z, x_min, x_max, y_min, y_max };
          }

          return z;
        }),
      );
      return;
    }

    // Draw rect
    if (!dragStart.current) return;
    const pos = getRelativePos(e);
    const x   = Math.min(dragStart.current.x, pos.x);
    const y   = Math.min(dragStart.current.y, pos.y);
    setDrawRect({ x, y, w: Math.abs(pos.x - dragStart.current.x), h: Math.abs(pos.y - dragStart.current.y) });
  };

  const handleMouseUp = () => {
    if (dragState) { setDragState(null); return; }

    if (!dragStart.current || !drawRect || drawRect.w < 10 || drawRect.h < 10) {
      dragStart.current = null;
      setDrawRect(null);
      return;
    }
    const topLeft     = toMetres(drawRect.x, drawRect.y);
    const bottomRight = toMetres(drawRect.x + drawRect.w, drawRect.y + drawRect.h);
    setPendingMetres({
      x_min: Math.round(topLeft.x * 100) / 100,
      x_max: Math.round(bottomRight.x * 100) / 100,
      y_min: Math.round(topLeft.y * 100) / 100,
      y_max: Math.round(bottomRight.y * 100) / 100,
    });
    dragStart.current = null;
    setDrawMode(false);
  };

  // ── saved zone handlers ──────────────────────────────────────────────────
  const handleSave = async (name: string, color: string, isHighRisk: boolean) => {
    if (!pendingMetres) return;
    setSavingZone(true);
    try {
      const zone = await createZone(buildingId, floor.id, { name, color, is_high_risk: isHighRisk, ...pendingMetres });
      setZones((z) => [...z, zone]);
      setPendingMetres(null);
      setDrawRect(null);
      toast.success(`Zone "${name}" saved`);
    } catch {
      toast.error("Failed to save zone");
    } finally {
      setSavingZone(false);
    }
  };

  const handleDelete = async (zoneId: string) => {
    setDeletingId(zoneId);
    try {
      await deleteZone(buildingId, floor.id, zoneId);
      setZones((z) => z.filter((zone) => zone.id !== zoneId));
      setSelectedIds((s) => { const n = new Set(s); n.delete(zoneId); return n; });
      toast.success("Zone deleted");
    } catch {
      toast.error("Failed to delete zone");
    } finally {
      setDeletingId(null);
    }
  };

  const toggleSelect  = (id: string) => setSelectedIds((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const selectAll     = () => setSelectedIds(new Set(zones.map((z) => z.id)));
  const clearSelection = () => setSelectedIds(new Set());

  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    setDeletingSelected(true);
    const ids = [...selectedIds];
    let deleted = 0;
    await Promise.all(ids.map(async (id) => {
      try { await deleteZone(buildingId, floor.id, id); deleted++; } catch { /* skip */ }
    }));
    setZones((z) => z.filter((zone) => !ids.includes(zone.id)));
    setSelectedIds(new Set());
    setDeletingSelected(false);
    toast.success(`${deleted} zone${deleted !== 1 ? "s" : ""} deleted`);
  };

  const handleClearAll = async () => {
    setConfirmClearAll(false);
    setDeletingSelected(true);
    let deleted = 0;
    await Promise.all(zones.map(async (z) => {
      try { await deleteZone(buildingId, floor.id, z.id); deleted++; } catch { /* skip */ }
    }));
    setZones([]);
    setSelectedIds(new Set());
    setDeletingSelected(false);
    toast.success(`All ${deleted} zone${deleted !== 1 ? "s" : ""} cleared`);
  };

  // ── AI detect handlers ───────────────────────────────────────────────────
  const handleAiDetect = async () => {
    setAiLoading(true);
    try {
      const suggestions = await aiDetectZones(buildingId, floor.id);
      setPendingZones(suggestions.map((s, i) => ({ ...s, _key: `ai-${i}-${Date.now()}` })));
      setSelectedKey(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "AI detection failed");
    } finally {
      setAiLoading(false);
    }
  };

  const handleSaveOnePending = async (suggestion: Suggestion) => {
    try {
      const { _key, ...data } = suggestion;
      const zone = await createZone(buildingId, floor.id, data);
      setZones((z) => [...z, zone]);
      setPendingZones((p) => p.filter((z) => z._key !== suggestion._key));
      if (selectedKey === suggestion._key) setSelectedKey(null);
      toast.success(`Zone "${suggestion.name}" saved`);
    } catch {
      toast.error("Failed to save zone");
    }
  };

  const handleSaveAllPending = async () => {
    if (pendingZones.length === 0) return;
    setSavingPending(true);
    let saved = 0;
    for (const s of pendingZones) {
      try {
        const { _key, ...data } = s;
        const zone = await createZone(buildingId, floor.id, data);
        setZones((z) => [...z, zone]);
        saved++;
      } catch { /* skip */ }
    }
    setPendingZones([]);
    setSelectedKey(null);
    setSavingPending(false);
    toast.success(`${saved} zone${saved !== 1 ? "s" : ""} saved`);
  };

  const commitPendingName = (key: string) => {
    setPendingZones((p) => p.map((z) => z._key === key ? { ...z, name: editingName.trim() || z.name } : z));
    setEditingNameKey(null);
  };

  const allSelected = zones.length > 0 && selectedIds.size === zones.length;

  return (
    <div className="space-y-4">
      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase mr-1">Zones</span>
        {isAdmin && (
          <>
            <button
              onClick={() => { setDrawMode((m) => !m); setPendingMetres(null); setDrawRect(null); }}
              disabled={!calibrated}
              title={calibrated ? undefined : "Calibrate this floor first"}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono transition-colors disabled:opacity-40 ${drawMode ? "bg-s-accent text-s-base" : "bg-s-elevated border border-s-border text-s-muted hover:text-s-text"}`}
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="3" y1="9" x2="21" y2="9"/></svg>
              {drawMode ? "Drawing…" : "Add Zone"}
            </button>
            <button
              onClick={handleAiDetect}
              disabled={!calibrated || aiLoading}
              title={calibrated ? undefined : "Calibrate this floor first"}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-s-elevated border border-s-border text-xs font-mono text-s-muted hover:text-s-text disabled:opacity-40 transition-colors"
            >
              {aiLoading
                ? <span className="h-3 w-3 rounded-full border-2 border-s-accent border-t-transparent animate-spin" />
                : <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>}
              {aiLoading ? "Analysing…" : "AI Detect"}
            </button>

            {/* Save / Discard pending AI zones */}
            {pendingZones.length > 0 && (
              <>
                <button
                  onClick={handleSaveAllPending}
                  disabled={savingPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-s-accent text-s-base text-xs font-mono font-bold hover:opacity-90 disabled:opacity-40 transition-opacity"
                >
                  {savingPending && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
                  Save {pendingZones.length} AI Zone{pendingZones.length !== 1 ? "s" : ""}
                </button>
                <button
                  onClick={() => { setPendingZones([]); setSelectedKey(null); }}
                  className="px-3 py-1.5 rounded-lg border border-s-border text-xs font-mono text-s-muted hover:text-s-text transition-colors"
                >
                  Discard
                </button>
              </>
            )}

            {zones.length > 0 && (
              confirmClearAll ? (
                <div className="flex items-center gap-1.5 rounded-lg border border-s-danger/40 bg-s-danger/10 px-3 py-1.5">
                  <span className="text-xs text-s-danger font-mono">Clear all {zones.length} zones?</span>
                  <button onClick={handleClearAll} disabled={deletingSelected} className="px-2 py-0.5 rounded bg-s-danger/30 text-xs text-s-danger hover:bg-s-danger/50 disabled:opacity-40 transition-colors font-mono">Yes</button>
                  <button onClick={() => setConfirmClearAll(false)} className="px-2 py-0.5 rounded border border-s-border text-xs text-s-muted hover:text-s-text transition-colors font-mono">No</button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmClearAll(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-s-elevated border border-s-border text-xs font-mono text-s-muted hover:text-s-danger hover:border-s-danger/40 transition-colors"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                  Clear All
                </button>
              )
            )}
          </>
        )}
        <button
          onClick={() => setShowZones((v) => !v)}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-s-elevated border border-s-border text-xs font-mono text-s-muted hover:text-s-text transition-colors"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            {showZones
              ? <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>
              : <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></>}
          </svg>
          {showZones ? "Hide Zones" : "Show Zones"}
        </button>
      </div>

      {aiLoading && (
        <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg border border-s-accent/40 bg-s-accent/10">
          <span className="h-3.5 w-3.5 shrink-0 rounded-full border-2 border-s-accent border-t-transparent animate-spin" />
          <p className="font-mono text-xs text-s-accent tracking-wide">AI is analysing floor plan… may take up to 30 s</p>
        </div>
      )}

      {pendingZones.length > 0 && (
        <div style={{ padding: "8px 12px", borderRadius: "6px", backgroundColor: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.3)", fontSize: "12px", color: "var(--text-secondary)" }}>
          ⚠️ AI-detected zones are approximate. Drag to reposition · drag handles to resize · double-click label to rename.
        </div>
      )}

      {!calibrated && isAdmin && (
        <p className="text-xs text-s-accent font-mono">Calibrate this floor first before adding zones.</p>
      )}

      {/* ── Canvas ──────────────────────────────────────────────────────── */}
      <div
        ref={containerRef}
        className="relative w-full rounded-xl overflow-hidden border border-s-border bg-s-elevated select-none"
        style={{ cursor: containerCursor }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={() => { if (!dragState) setSelectedKey(null); }}
      >
        <img
          src={floor.url}
          alt={floor.name}
          className="w-full h-auto pointer-events-none"
          onLoad={(e) => { const img = e.currentTarget; setNaturalSize({ w: img.naturalWidth, h: img.naturalHeight }); }}
          draggable={false}
        />

        {/* Saved zones */}
        {showZones && naturalSize && zones.map((zone) => (
          <div
            key={zone.id}
            className="absolute group"
            style={{
              left: `${toPct(zone.x_min, "x")}%`,
              top:  `${toPct(zone.y_min, "y")}%`,
              width: `${toPct(zone.x_max - zone.x_min, "x")}%`,
              height: `${toPct(zone.y_max - zone.y_min, "y")}%`,
              backgroundColor: zone.color,
              border: `1px solid ${colorSolid(zone.color)}66`,
              borderRadius: 4,
              pointerEvents: drawMode ? "none" : "auto",
            }}
          >
            <div className="absolute inset-0 flex items-center justify-center p-1 pointer-events-none">
              <span className="font-mono text-[10px] font-bold text-center leading-tight truncate max-w-full" style={{ color: colorSolid(zone.color), textShadow: "0 1px 2px rgba(0,0,0,0.5)" }}>
                {zone.is_high_risk && "⚠ "}{zone.name}
              </span>
            </div>
            {isAdmin && (
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(zone.id); }}
                disabled={deletingId === zone.id}
                className="absolute top-1 right-1 h-5 w-5 rounded-full bg-black/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-s-danger/80 disabled:opacity-40"
                title="Delete zone"
              >
                {deletingId === zone.id
                  ? <span className="h-2.5 w-2.5 rounded-full border border-white border-t-transparent animate-spin" />
                  : <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>}
              </button>
            )}
          </div>
        ))}

        {/* Pending AI zones */}
        {naturalSize && pendingZones.map((zone) => {
          const isSelected  = selectedKey === zone._key;
          const toolbarBelow = toPct(zone.y_min, "y") < 12;

          return (
            <div
              key={zone._key}
              className="absolute group"
              style={{
                left:   `${toPct(zone.x_min, "x")}%`,
                top:    `${toPct(zone.y_min, "y")}%`,
                width:  `${toPct(zone.x_max - zone.x_min, "x")}%`,
                height: `${toPct(zone.y_max - zone.y_min, "y")}%`,
                backgroundColor: zone.color,
                border: `1.5px dashed ${colorSolid(zone.color)}cc`,
                borderRadius: 4,
                cursor: "move",
                zIndex: isSelected ? 5 : 2,
                overflow: "visible",
                pointerEvents: drawMode ? "none" : "auto",
              }}
              onMouseDown={(e) => {
                if (e.button !== 0) return;
                e.stopPropagation();
                setSelectedKey(zone._key);
                const pos = getRelativePos(e);
                setDragState({
                  key: zone._key, mode: "move",
                  startX: pos.x, startY: pos.y,
                  origZone: { x_min: zone.x_min, x_max: zone.x_max, y_min: zone.y_min, y_max: zone.y_max },
                });
              }}
              onDoubleClick={(e) => { e.stopPropagation(); setEditingNameKey(zone._key); setEditingName(zone.name); }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Label / inline name editor */}
              <div className="absolute inset-0 flex items-center justify-center p-1">
                {editingNameKey === zone._key ? (
                  <input
                    autoFocus
                    value={editingName}
                    onChange={(e) => setEditingName(e.target.value)}
                    onBlur={() => commitPendingName(zone._key)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitPendingName(zone._key);
                      if (e.key === "Escape") setEditingNameKey(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                    className="w-full text-center bg-s-surface/90 border border-s-accent rounded px-1 py-0.5 text-[10px] font-mono text-s-text focus:outline-none"
                    style={{ maxWidth: "90%" }}
                  />
                ) : (
                  <span className="font-mono text-[10px] font-bold text-center leading-tight truncate max-w-full pointer-events-none" style={{ color: colorSolid(zone.color), textShadow: "0 1px 2px rgba(0,0,0,0.5)" }}>
                    {zone.is_high_risk && "⚠ "}{zone.name}
                  </span>
                )}
              </div>

              {/* Floating toolbar */}
              {isSelected && (
                <div
                  className="absolute left-0 flex items-center gap-1"
                  style={{
                    ...(toolbarBelow ? { top: "100%", marginTop: 4 } : { bottom: "100%", marginBottom: 4 }),
                    backgroundColor: "var(--bg-elevated)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    padding: "4px 8px",
                    zIndex: 20,
                    fontSize: 11,
                    whiteSpace: "nowrap",
                    pointerEvents: "auto",
                  }}
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Rename */}
                  <button
                    title="Rename"
                    onClick={() => { setEditingNameKey(zone._key); setEditingName(zone.name); }}
                    className="text-s-muted hover:text-s-text transition-colors p-0.5"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                  </button>
                  {/* Save this zone */}
                  <button
                    title="Save this zone"
                    onClick={() => handleSaveOnePending(zone)}
                    className="text-s-accent hover:opacity-70 transition-opacity p-0.5 font-mono font-bold text-xs"
                  >
                    ✓
                  </button>
                  {/* Delete */}
                  <button
                    title="Discard"
                    onClick={() => { setPendingZones((p) => p.filter((z) => z._key !== zone._key)); setSelectedKey(null); }}
                    className="text-s-muted hover:text-s-danger transition-colors p-0.5"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </div>
              )}

              {/* Resize handles */}
              {HANDLES.map(({ id, top, left, cursor }) => (
                <div
                  key={id}
                  className={`absolute ${isSelected ? "opacity-100" : "opacity-0 group-hover:opacity-100"} transition-opacity`}
                  style={{
                    top, left,
                    width: 8, height: 8,
                    transform: "translate(-50%, -50%)",
                    backgroundColor: "var(--accent)",
                    border: "1px solid white",
                    borderRadius: 2,
                    cursor,
                    zIndex: 10,
                    pointerEvents: "auto",
                  }}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    const pos = getRelativePos(e);
                    setDragState({
                      key: zone._key, mode: "resize", handle: id,
                      startX: pos.x, startY: pos.y,
                      origZone: { x_min: zone.x_min, x_max: zone.x_max, y_min: zone.y_min, y_max: zone.y_max },
                    });
                  }}
                />
              ))}
            </div>
          );
        })}

        {/* Draw rect preview */}
        {drawRect && (
          <div className="absolute pointer-events-none" style={{ left: drawRect.x, top: drawRect.y, width: drawRect.w, height: drawRect.h, border: "2px dashed var(--accent)", borderRadius: 4, backgroundColor: "rgba(245,158,11,0.08)" }} />
        )}

        {drawMode && !drawRect && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="bg-black/60 rounded-lg px-4 py-2"><p className="font-mono text-xs text-white tracking-wide">Click and drag to draw a zone</p></div>
          </div>
        )}
      </div>

      {pendingMetres && (
        <ZoneForm onSave={handleSave} onCancel={() => { setPendingMetres(null); setDrawRect(null); }} saving={savingZone} />
      )}

      {/* ── Saved zones table ────────────────────────────────────────────── */}
      {zones.length > 0 && (
        <div className="space-y-2">
          {isAdmin && selectedIds.size > 0 && (
            <div className="flex items-center gap-2 px-4 py-2 rounded-lg border border-s-accent/30 bg-s-accent/10">
              <span className="flex-1 font-mono text-xs text-s-accent">{selectedIds.size} zone{selectedIds.size !== 1 ? "s" : ""} selected</span>
              <button onClick={clearSelection} className="text-xs text-s-muted hover:text-s-text transition-colors px-2 py-1 font-mono">Deselect</button>
              <button onClick={handleDeleteSelected} disabled={deletingSelected} className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-s-danger/20 border border-s-danger/30 text-xs font-mono text-s-danger hover:bg-s-danger/30 disabled:opacity-40 transition-colors">
                {deletingSelected && <span className="h-2.5 w-2.5 rounded-full border border-s-danger border-t-transparent animate-spin" />}
                Delete {selectedIds.size} selected
              </button>
            </div>
          )}
          <div className="bento-card p-0 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-s-border">
                  {isAdmin && (
                    <th className="px-4 py-2.5 w-8">
                      <input type="checkbox" checked={allSelected} onChange={(e) => e.target.checked ? selectAll() : clearSelection()} className="accent-amber-500 cursor-pointer" title={allSelected ? "Deselect all" : "Select all"} />
                    </th>
                  )}
                  {["Zone", "Type", "High Risk", "Bounds (m)"].map((h) => (
                    <th key={h} className="font-mono text-[10px] text-s-muted tracking-widest uppercase text-left px-4 py-2.5">{h}</th>
                  ))}
                  {isAdmin && <th className="px-4 py-2.5" />}
                </tr>
              </thead>
              <tbody>
                {zones.map((zone) => (
                  <tr key={zone.id} className={`border-b border-s-border/50 last:border-0 transition-colors ${selectedIds.has(zone.id) ? "bg-s-accent/5" : "hover:bg-s-elevated"}`}>
                    {isAdmin && (
                      <td className="px-4 py-2.5 w-8">
                        <input type="checkbox" checked={selectedIds.has(zone.id)} onChange={() => toggleSelect(zone.id)} className="accent-amber-500 cursor-pointer" />
                      </td>
                    )}
                    <td className="px-4 py-2.5 flex items-center gap-2">
                      <span className="h-2.5 w-2.5 rounded-sm shrink-0" style={{ backgroundColor: colorSolid(zone.color) }} />
                      <span className="text-s-text font-medium truncate">{zone.name}</span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[10px] text-s-muted">{COLOR_PRESETS.find((p) => p.value === zone.color)?.label ?? "Custom"}</td>
                    <td className="px-4 py-2.5">{zone.is_high_risk ? <span className="font-mono text-[9px] px-1.5 py-0.5 rounded bg-s-danger/20 text-s-danger">YES</span> : <span className="font-mono text-[9px] text-s-muted">—</span>}</td>
                    <td className="px-4 py-2.5 font-mono text-[10px] text-s-muted">({zone.x_min},{zone.y_min}) → ({zone.x_max},{zone.y_max})</td>
                    {isAdmin && (
                      <td className="px-4 py-2.5">
                        <button onClick={() => handleDelete(zone.id)} disabled={deletingId === zone.id} className="text-s-muted hover:text-s-danger transition-colors disabled:opacity-40" title="Delete zone">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!isLoading && zones.length === 0 && pendingZones.length === 0 && !pendingMetres && (
        <p className="font-mono text-[10px] text-s-muted text-center py-4 tracking-widest">
          {calibrated ? "No zones defined. Draw zones or use AI Detect." : "No zones defined."}
        </p>
      )}
    </div>
  );
}
