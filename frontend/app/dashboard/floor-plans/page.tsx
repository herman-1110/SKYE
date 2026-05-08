"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/hooks/useAuth";
import { useBuildings } from "@/hooks/useBuildings";
import { useFloors } from "@/hooks/useFloors";
import {
  createBuilding,
  deleteBuilding,
  renameBuilding,
} from "@/services/buildingService";
import {
  activateFloor,
  deactivateFloor,
  deleteFloor,
  renameFloor,
  uploadFloor,
} from "@/services/floorService";
import { toast } from "@/store/toastStore";
import CalibrationTool from "@/components/map/CalibrationTool";
import ZoneEditor from "@/components/map/ZoneEditor";
import type { BuildingRecord } from "@/types/building";
import type { FloorRecord } from "@/types/floor";

// ─── Skeleton ────────────────────────────────────────────────────────────────
function PageSkeleton() {
  return (
    <div className="max-w-[1400px] mx-auto px-8 py-8 flex gap-6 h-[calc(100vh-5rem)]">
      <div className="w-72 shrink-0 space-y-3">
        <div className="h-3 bg-s-elevated rounded w-24 animate-pulse" />
        {[1, 2, 3].map((i) => <div key={i} className="h-16 bento-card animate-pulse" />)}
      </div>
      <div className="flex-1 space-y-3">
        <div className="h-3 bg-s-elevated rounded w-32 animate-pulse" />
        {[1, 2].map((i) => <div key={i} className="h-24 bento-card animate-pulse" />)}
      </div>
    </div>
  );
}

// ─── Inline editable text ────────────────────────────────────────────────────
function InlineEdit({
  value,
  onSave,
  className = "",
  startEditTrigger = 0,
}: {
  value: string;
  onSave: (v: string) => void;
  className?: string;
  startEditTrigger?: number;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (startEditTrigger > 0) {
      setDraft(value);
      setEditing(true);
      setTimeout(() => inputRef.current?.select(), 0);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startEditTrigger]);

  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== value) onSave(trimmed);
    setEditing(false);
  };

  if (!editing) {
    return (
      <span
        className={`cursor-text hover:underline decoration-dashed underline-offset-2 ${className}`}
        onDoubleClick={() => { setDraft(value); setEditing(true); setTimeout(() => inputRef.current?.select(), 0); }}
        title="Double-click to rename"
      >
        {value}
      </span>
    );
  }

  return (
    <input
      ref={inputRef}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(false); }}
      className={`bg-s-elevated border border-s-border rounded px-2 py-0.5 focus:outline-none focus:border-s-accent ${className}`}
    />
  );
}

// ─── Delete Floor Modal ───────────────────────────────────────────────────────
function DeleteFloorModal({
  floor,
  onClose,
  onConfirm,
}: {
  floor: FloorRecord;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try { await onConfirm(); }
    finally { setDeleting(false); }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape" && !deleting) onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, deleting]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget && !deleting) onClose(); }}
    >
      <div className="w-full max-w-sm rounded-xl overflow-hidden" style={{ background: "var(--glass-bg)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", border: "1px solid var(--glass-border)", boxShadow: "var(--glass-shadow)" }}>
        <div className="px-5 py-5 space-y-4">
          <div className="flex items-start gap-3">
            <div className="h-8 w-8 rounded-lg bg-s-danger/15 flex items-center justify-center shrink-0 mt-0.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-s-danger">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
              </svg>
            </div>
            <div>
              <p className="text-sm font-semibold text-s-text">Delete &ldquo;{floor.name}&rdquo;?</p>
              <p className="text-xs text-s-muted mt-0.5">This will permanently delete:</p>
            </div>
          </div>
          <ul className="space-y-1 pl-4">
            {[
              "The floor plan image",
              "All calibration data",
              "All zones on this floor",
            ].map((item) => (
              <li key={item} className="flex items-center gap-2 text-xs text-s-muted">
                <span className="h-1 w-1 rounded-full bg-s-muted shrink-0" />
                {item}
              </li>
            ))}
          </ul>
          <p className="text-xs text-s-danger font-mono tracking-wide">This action cannot be undone.</p>
        </div>
        <div className="flex gap-2 px-5 py-4 border-t border-s-border">
          <button onClick={onClose} disabled={deleting} className="flex-1 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors disabled:opacity-40">
            Cancel
          </button>
          <button onClick={handleDelete} disabled={deleting} className="flex-1 py-2 rounded-lg bg-s-danger text-white font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
            {deleting && <span className="h-3 w-3 rounded-full border-2 border-white border-t-transparent animate-spin" />}
            {deleting ? "Deleting…" : "Delete Floor"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── New Building Modal ───────────────────────────────────────────────────────
function NewBuildingModal({ onClose, onCreated }: { onClose: () => void; onCreated: (b: BuildingRecord) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const b = await createBuilding(name.trim(), description.trim());
      onCreated(b);
      onClose();
    } catch {
      toast.error("Failed to create building.");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape" && !saving) onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, saving]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={(e) => { if (e.target === e.currentTarget && !saving) onClose(); }}
    >
      <div className="w-full max-w-sm rounded-xl overflow-hidden" style={{ background: "var(--glass-bg)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", border: "1px solid var(--glass-border)", boxShadow: "var(--glass-shadow)" }}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-s-border">
          <h2 className="font-mono text-xs text-s-muted tracking-widest uppercase">New Building</h2>
          <button onClick={onClose} className="text-s-muted hover:text-s-text transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div className="px-5 py-4 space-y-3">
          <div className="space-y-1.5">
            <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Building Name</label>
            <input autoFocus type="text" placeholder='e.g. Warehouse A' value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleCreate()} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
          </div>
          <div className="space-y-1.5">
            <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Description <span className="normal-case text-[9px]">(optional)</span></label>
            <input type="text" placeholder='e.g. Main logistics hub' value={description} onChange={(e) => setDescription(e.target.value)} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
          </div>
        </div>
        <div className="flex gap-2 px-5 py-4 border-t border-s-border">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors">Cancel</button>
          <button onClick={handleCreate} disabled={saving || !name.trim()} className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
            {saving && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
            {saving ? "Creating…" : "Create Building"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Add Floor Modal ─────────────────────────────────────────────────────────
function AddFloorModal({
  buildingId,
  existingCount,
  onClose,
}: {
  buildingId: string;
  existingCount: number;
  onClose: () => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [floorNumber, setFloorNumber] = useState(String(existingCount + 1));
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const ACCEPTED = ["image/png", "image/jpeg", "image/jpg", "image/webp", "application/pdf"];

  const handleFile = (f: File) => {
    if (!ACCEPTED.includes(f.type)) { setError("PNG, JPG, WEBP or PDF only."); return; }
    if (f.size > 10 * 1024 * 1024) { setError("Max 10 MB."); return; }
    if (preview) URL.revokeObjectURL(preview);
    setFile(f);
    setPreview(f.type.startsWith("image/") ? URL.createObjectURL(f) : null);
    setError(null);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape" && progress === null) onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose, progress]);

  const handleUpload = async () => {
    if (!file || !name.trim()) return;
    const num = parseInt(floorNumber, 10);
    if (!num || num < 1) { setError("Enter a valid floor number."); return; }
    setError(null);
    setProgress(0);
    try {
      await uploadFloor(file, buildingId, name.trim(), num, setProgress);
      toast.success(`Floor "${name}" uploaded`);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setProgress(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-sm rounded-xl overflow-hidden" style={{ background: "var(--glass-bg)", backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)", border: "1px solid var(--glass-border)", boxShadow: "var(--glass-shadow)" }}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-s-border">
          <h2 className="font-mono text-xs text-s-muted tracking-widest uppercase">Add Floor</h2>
          <button onClick={onClose} className="text-s-muted hover:text-s-text transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div className="px-5 py-4 space-y-3 max-h-[70vh] overflow-y-auto">
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-2 space-y-1.5">
              <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Floor Name</label>
              <input autoFocus type="text" placeholder='e.g. Level 1' value={name} onChange={(e) => setName(e.target.value)} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors" />
            </div>
            <div className="space-y-1.5">
              <label className="font-mono text-[10px] text-s-muted tracking-widest uppercase">Order</label>
              <input type="number" min="1" value={floorNumber} onChange={(e) => setFloorNumber(e.target.value)} className="w-full bg-s-elevated border border-s-border rounded-lg px-3 py-2 text-sm text-s-text focus:outline-none focus:border-s-accent transition-colors" />
            </div>
          </div>

          {file ? (
            <div className="border border-s-border rounded-lg overflow-hidden">
              {preview ? (
                <img src={preview} alt={file.name} className="w-full h-32 object-cover" />
              ) : (
                <div className="h-20 bg-s-elevated flex items-center justify-center text-s-muted">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                </div>
              )}
              <div className="flex items-center justify-between px-3 py-2 bg-s-elevated border-t border-s-border">
                <p className="text-xs text-s-text truncate">{file.name}</p>
                <button onClick={() => { setFile(null); setPreview(null); }} className="text-s-muted hover:text-s-danger ml-2 shrink-0 transition-colors">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>
          ) : (
            <div
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
              className={`flex flex-col items-center justify-center gap-2 border border-dashed rounded-lg px-4 py-6 cursor-pointer transition-colors ${dragOver ? "border-s-accent bg-s-accent/5" : "border-s-border hover:border-s-accent"}`}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={dragOver ? "text-s-accent" : "text-s-muted"}>
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <p className="text-xs text-s-muted text-center">Drop floor plan image or click to browse</p>
              <p className="font-mono text-[9px] text-s-muted tracking-widest">PNG, JPG, PDF · Max 10 MB</p>
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/jpg,image/webp,application/pdf" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }} />
            </div>
          )}

          {progress !== null && (
            <div className="space-y-1">
              <div className="h-1.5 w-full bg-s-border rounded-full overflow-hidden">
                <div className="h-full bg-s-accent rounded-full transition-all duration-200" style={{ width: `${progress}%` }} />
              </div>
              <p className="font-mono text-[10px] text-s-muted tracking-widest">{progress}% UPLOADED</p>
            </div>
          )}

          {error && (
            <p className="text-xs text-s-danger bg-s-danger/10 border border-s-danger/30 rounded-lg px-3 py-2">{error}</p>
          )}
        </div>
        <div className="flex gap-2 px-5 py-4 border-t border-s-border">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-s-border text-xs text-s-muted hover:text-s-text transition-colors">Cancel</button>
          <button onClick={handleUpload} disabled={progress !== null || !name.trim() || !file} className="flex-1 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5">
            {progress !== null && <span className="h-3 w-3 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
            {progress !== null ? "Uploading…" : "Upload Floor"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Floor Card ───────────────────────────────────────────────────────────────
function FloorCard({
  building,
  floor,
  isAdmin,
  zonesOpenForId,
  onToggleZones,
  onCalibrate,
  onActivate,
  onDeactivate,
  onRename,
  onDelete,
}: {
  building: BuildingRecord;
  floor: FloorRecord;
  isAdmin: boolean;
  zonesOpenForId: string | null;
  onToggleZones: (id: string) => void;
  onCalibrate: (floor: FloorRecord) => void;
  onActivate: (id: string) => void;
  onDeactivate: (id: string) => void;
  onRename: (id: string, name: string) => void;
  onDelete: (floor: FloorRecord) => Promise<void>;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0 });
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [renameTrigger, setRenameTrigger] = useState(0);
  const [busy, setBusy] = useState(false);
  const menuBtnRef = useRef<HTMLButtonElement>(null);

  const openMenu = () => {
    const rect = menuBtnRef.current?.getBoundingClientRect();
    if (!rect) return;
    const menuWidth = 168;
    const menuHeight = 220;
    const gap = 8;
    const wouldOverflowRight = rect.right + gap + menuWidth > window.innerWidth;
    const wouldOverflowBottom = rect.bottom + menuHeight > window.innerHeight;
    setMenuPos({
      left: wouldOverflowRight ? rect.left - menuWidth - gap : rect.right + gap,
      top: (wouldOverflowBottom ? rect.top - menuHeight : rect.bottom) + window.scrollY,
    });
    setMenuOpen((v) => !v);
  };

  const handleActivate = async () => {
    setMenuOpen(false);
    setBusy(true);
    try { await onActivate(floor.id); }
    finally { setBusy(false); }
  };

  const handleDeactivate = async () => {
    setMenuOpen(false);
    setBusy(true);
    try { await onDeactivate(floor.id); }
    finally { setBusy(false); }
  };

  const handleRename = () => {
    setMenuOpen(false);
    setRenameTrigger((v) => v + 1);
  };

  const handleCalibrate = () => {
    setMenuOpen(false);
    onCalibrate(floor);
  };

  const handleManageZones = () => {
    setMenuOpen(false);
    onToggleZones(floor.id);
  };

  return (
    <div className="bento-card space-y-0 p-0" style={{ overflow: "visible" }}>
      <div className="flex items-center gap-3 px-4 py-3">
        {/* Thumbnail */}
        <div className="h-14 w-20 rounded-lg overflow-hidden shrink-0 bg-s-elevated border border-s-border">
          <img src={floor.url} alt={floor.name} className="h-full w-full object-cover" onError={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = "0"; }} />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {isAdmin ? (
              <InlineEdit
                value={floor.name}
                onSave={(v) => onRename(floor.id, v)}
                startEditTrigger={renameTrigger}
                className="text-sm font-semibold text-s-text"
              />
            ) : (
              <span className="text-sm font-semibold text-s-text truncate">{floor.name}</span>
            )}
            {floor.is_active && (
              <span className="font-mono text-[9px] px-1.5 py-0.5 rounded-full bg-s-success/20 text-s-success tracking-widest">ACTIVE</span>
            )}
          </div>
          <p className="font-mono text-[10px] text-s-muted mt-0.5">
            {floor.scale_pixels_per_meter
              ? `Calibrated: ${floor.scale_pixels_per_meter} px/m`
              : <span className="text-s-accent">⚠ Not calibrated</span>}
          </p>
        </div>

        {/* Actions */}
        {isAdmin && (
          <div className="flex items-center gap-1.5 shrink-0">
            {/* ⋯ button */}
            <button
              ref={menuBtnRef}
              onClick={openMenu}
              className="p-1.5 rounded-lg bg-s-elevated border border-s-border text-s-muted hover:text-s-text transition-colors"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* Zone editor — expands inline */}
      {zonesOpenForId === floor.id && (
        <div className="border-t border-s-border px-4 py-4">
          <ZoneEditor buildingId={building.id} floor={floor} isAdmin={isAdmin} />
        </div>
      )}

      {/* ⋯ dropdown — portal so it's never clipped by any parent */}
      {menuOpen && createPortal(
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 9998 }} onClick={() => setMenuOpen(false)} />
          <div
            style={{
              position: "absolute",
              top: menuPos.top,
              left: menuPos.left,
              width: 160,
              zIndex: 9999,
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              boxShadow: "0 4px 16px var(--shadow)",
              borderRadius: 10,
              padding: "4px 0",
            }}
          >
            {!floor.is_active ? (
              <button onClick={handleActivate} disabled={busy} style={{ fontSize: 13, padding: "6px 12px" }} className="w-full text-left text-s-text hover:bg-s-elevated transition-colors flex items-center gap-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Set as Active
              </button>
            ) : (
              <button onClick={handleDeactivate} disabled={busy} style={{ fontSize: 13, padding: "6px 12px" }} className="w-full text-left text-s-muted hover:bg-s-elevated transition-colors flex items-center gap-2">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                Deactivate
              </button>
            )}
            <button onClick={handleRename} style={{ fontSize: 13, padding: "6px 12px" }} className="w-full text-left text-s-text hover:bg-s-elevated transition-colors flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              Rename
            </button>
            <button onClick={handleCalibrate} style={{ fontSize: 13, padding: "6px 12px" }} className="w-full text-left text-s-text hover:bg-s-elevated transition-colors flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
              {floor.scale_pixels_per_meter ? "Recalibrate" : "Calibrate Scale"}
            </button>
            <button onClick={handleManageZones} style={{ fontSize: 13, padding: "6px 12px" }} className="w-full text-left text-s-text hover:bg-s-elevated transition-colors flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>
              Manage Zones
            </button>
            <div className="border-t border-s-border my-1" />
            <button
              onClick={() => { setMenuOpen(false); setShowDeleteModal(true); }}
              style={{ fontSize: 13, padding: "6px 12px" }}
              className="w-full text-left text-s-danger hover:bg-s-elevated transition-colors flex items-center gap-2"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>
              Delete Floor
            </button>
          </div>
        </>,
        document.body
      )}

      {/* Delete confirmation modal */}
      {showDeleteModal && (
        <DeleteFloorModal
          floor={floor}
          onClose={() => setShowDeleteModal(false)}
          onConfirm={async () => {
            await onDelete(floor);
            setShowDeleteModal(false);
          }}
        />
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function FloorPlansPage() {
  const { user, userRecord } = useAuth();
  const isAdmin = userRecord?.role === "admin";
  const { buildings, isLoading: buildingsLoading } = useBuildings();

  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null);
  const { floors, isLoading: floorsLoading } = useFloors(selectedBuildingId);

  const [showNewBuilding, setShowNewBuilding] = useState(false);
  const [showAddFloor, setShowAddFloor] = useState(false);
  const [calibratingFloor, setCalibratingFloor] = useState<FloorRecord | null>(null);
  const [zonesOpenForId, setZonesOpenForId] = useState<string | null>(null);
  const [deletingBuildingId, setDeletingBuildingId] = useState<string | null>(null);

  // Auto-select first building
  useEffect(() => {
    if (buildings.length > 0 && !selectedBuildingId) {
      setSelectedBuildingId(buildings[0].id);
    }
  }, [buildings, selectedBuildingId]);

  const selectedBuilding = buildings.find((b) => b.id === selectedBuildingId) ?? null;

  const handleRenameBuilding = async (id: string, name: string) => {
    try { await renameBuilding(id, name); }
    catch { toast.error("Rename failed."); }
  };

  const handleDeleteBuilding = async (id: string) => {
    setDeletingBuildingId(id);
    try {
      await deleteBuilding(id);
      if (selectedBuildingId === id) setSelectedBuildingId(null);
      toast.success("Building deleted");
    } catch {
      toast.error("Delete failed.");
    } finally {
      setDeletingBuildingId(null);
    }
  };

  const handleRenameFloor = async (floorId: string, name: string) => {
    if (!selectedBuildingId) return;
    try { await renameFloor(selectedBuildingId, floorId, name); }
    catch { toast.error("Rename failed."); }
  };

  const handleActivateFloor = async (floorId: string) => {
    if (!selectedBuildingId) return;
    try { await activateFloor(selectedBuildingId, floorId); toast.success("Floor activated"); }
    catch { toast.error("Activation failed."); }
  };

  const handleDeactivateFloor = async (floorId: string) => {
    if (!selectedBuildingId) return;
    try { await deactivateFloor(selectedBuildingId, floorId); toast.success("Floor deactivated"); }
    catch { toast.error("Deactivation failed."); }
  };

  const handleDeleteFloor = async (floor: FloorRecord) => {
    if (!selectedBuildingId) return;
    try {
      await deleteFloor(selectedBuildingId, floor.id, floor.storage_path);
      toast.success(`Floor "${floor.name}" deleted`);
    } catch {
      toast.error("Delete failed.");
    }
  };

  const toggleZones = (floorId: string) => {
    setZonesOpenForId((prev) => (prev === floorId ? null : floorId));
  };

  if (buildingsLoading) return <PageSkeleton />;

  return (
    <div className="max-w-[1400px] mx-auto px-8 py-8">
      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">
          Floor Plans
        </h1>
        {isAdmin && (
          <button
            onClick={() => setShowNewBuilding(true)}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 transition-opacity"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            New Building
          </button>
        )}
      </div>

      {buildings.length === 0 ? (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-24 text-center space-y-5">
          <div className="h-14 w-14 rounded-xl bg-s-elevated border border-s-border flex items-center justify-center">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-muted">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
          </div>
          <div className="space-y-1.5">
            <p className="text-sm font-semibold text-s-text">No Buildings</p>
            <p className="text-xs text-s-muted max-w-xs leading-relaxed">
              {isAdmin
                ? "Create a building to start organising your floor plans."
                : "No floor plans have been set up yet. Contact your administrator."}
            </p>
          </div>
          {isAdmin && (
            <button onClick={() => setShowNewBuilding(true)} className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-s-accent text-s-base font-bold text-sm hover:opacity-90 transition-opacity">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              Create First Building
            </button>
          )}
        </div>
      ) : (
        /* Two-column layout */
        <div className="flex gap-6 items-start">
          {/* Left: Buildings list */}
          <div className="w-64 shrink-0 space-y-2">
            <p className="font-mono text-[10px] text-s-muted tracking-widest uppercase mb-2">Buildings ({buildings.length})</p>
            {buildings.map((b) => (
              <div
                key={b.id}
                onClick={() => setSelectedBuildingId(b.id)}
                className={`group relative rounded-xl px-4 py-3 cursor-pointer transition-colors border ${selectedBuildingId === b.id ? "bg-s-elevated border-s-accent" : "bg-s-surface border-s-border hover:bg-s-elevated"}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    {isAdmin ? (
                      <InlineEdit
                        value={b.name}
                        onSave={(v) => handleRenameBuilding(b.id, v)}
                        className="text-sm font-semibold text-s-text block"
                      />
                    ) : (
                      <p className="text-sm font-semibold text-s-text truncate">{b.name}</p>
                    )}
                    {b.description && (
                      <p className="text-xs text-s-muted truncate mt-0.5">{b.description}</p>
                    )}
                  </div>
                  {isAdmin && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteBuilding(b.id); }}
                      disabled={deletingBuildingId === b.id}
                      className="opacity-0 group-hover:opacity-100 shrink-0 text-s-muted hover:text-s-danger transition-all disabled:opacity-40"
                      title="Delete building"
                    >
                      {deletingBuildingId === b.id ? (
                        <span className="h-3 w-3 rounded-full border border-s-muted border-t-transparent animate-spin block" />
                      ) : (
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                          <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
                        </svg>
                      )}
                    </button>
                  )}
                </div>
              </div>
            ))}

            {isAdmin && (
              <button
                onClick={() => setShowNewBuilding(true)}
                className="w-full flex items-center justify-center gap-1.5 py-2 rounded-xl border border-dashed border-s-border text-xs text-s-muted hover:border-s-accent hover:text-s-text transition-colors"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                New Building
              </button>
            )}
          </div>

          {/* Right: Floors for selected building */}
          <div className="flex-1 min-w-0 space-y-4">
            {selectedBuilding ? (
              <>
                <div className="flex items-center justify-between">
                  <p className="font-mono text-[10px] text-s-muted tracking-widest uppercase">
                    {selectedBuilding.name} — Floors ({floors.length})
                  </p>
                  {isAdmin && (
                    <button
                      onClick={() => setShowAddFloor(true)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 transition-opacity"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                      Add Floor
                    </button>
                  )}
                </div>

                {floorsLoading ? (
                  <div className="space-y-3">
                    {[1, 2].map((i) => <div key={i} className="h-24 bento-card animate-pulse" />)}
                  </div>
                ) : floors.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center gap-4">
                    <p className="text-sm text-s-text font-medium">No floors yet</p>
                    <p className="text-xs text-s-muted max-w-xs">
                      {isAdmin ? "Add a floor plan image for this building." : "No floors uploaded yet."}
                    </p>
                    {isAdmin && (
                      <button onClick={() => setShowAddFloor(true)} className="px-4 py-2 rounded-lg bg-s-accent text-s-base font-bold text-xs hover:opacity-90 transition-opacity">
                        Add First Floor
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {floors.map((floor) => (
                      <FloorCard
                        key={floor.id}
                        building={selectedBuilding}
                        floor={floor}
                        isAdmin={isAdmin}
                        zonesOpenForId={zonesOpenForId}
                        onToggleZones={toggleZones}
                        onCalibrate={setCalibratingFloor}
                        onActivate={handleActivateFloor}
                        onDeactivate={handleDeactivateFloor}
                        onRename={handleRenameFloor}
                        onDelete={handleDeleteFloor}
                      />
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="flex items-center justify-center h-40 text-s-muted text-sm">
                Select a building to view its floors
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      {showNewBuilding && (
        <NewBuildingModal
          onClose={() => setShowNewBuilding(false)}
          onCreated={(b) => setSelectedBuildingId(b.id)}
        />
      )}

      {showAddFloor && selectedBuildingId && (
        <AddFloorModal
          buildingId={selectedBuildingId}
          existingCount={floors.length}
          onClose={() => setShowAddFloor(false)}
        />
      )}

      {calibratingFloor && selectedBuildingId && (
        <CalibrationTool
          buildingId={selectedBuildingId}
          floor={calibratingFloor}
          onClose={() => setCalibratingFloor(null)}
          onCalibrated={() => setCalibratingFloor(null)}
        />
      )}
    </div>
  );
}
