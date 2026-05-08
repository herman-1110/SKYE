"use client";
import { useState, useEffect } from "react";
import { activateFloorPlan, updateScale, deleteFloorPlan } from "@/services/floorPlanService";
import { toast } from "@/store/toastStore";
import type { FloorPlanRecord } from "@/types/floorPlan";

interface Props {
  plans: FloorPlanRecord[];
  userId: string;
  isAdmin?: boolean;
}

function getTypeLabel(url: string, name: string): string {
  const s = (url + name).toLowerCase();
  if (s.includes(".pdf")) return "PDF";
  if (s.includes(".png")) return "PNG";
  if (s.includes(".jpg") || s.includes(".jpeg")) return "JPG";
  if (s.includes(".webp")) return "WEBP";
  return "IMAGE";
}

function PdfThumbnail({ name }: { name: string }) {
  return (
    <div className="w-full h-full flex flex-col items-center justify-center gap-2 bg-s-accent/5">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-s-accent">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/>
        <polyline points="10 9 9 9 8 9"/>
      </svg>
      <p className="font-mono text-[9px] tracking-widest text-s-muted px-4 text-center truncate max-w-full">{name}</p>
    </div>
  );
}

function Lightbox({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-lg bg-white/10 text-white hover:bg-white/20 transition-colors"
        aria-label="Close"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
      <img
        src={src}
        alt={alt}
        className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

export default function FloorPlanList({ plans, userId, isAdmin = false }: Props) {
  const [scaleInputs, setScaleInputs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);

  const handleActivate = async (id: string) => {
    setBusy(id + "-activate");
    try {
      await activateFloorPlan(id, userId);
      toast.success("Floor plan activated");
    } catch {
      toast.error("Activation failed. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const handleScaleSave = async (id: string) => {
    const val = parseFloat(scaleInputs[id] ?? "");
    if (!val || val <= 0) return;
    setBusy(id + "-scale");
    try {
      await updateScale(id, val);
      toast.success("Scale updated");
    } catch {
      toast.error("Scale update failed. Please try again.");
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async (id: string) => {
    const plan = plans.find((p) => p.floor_plan_id === id);
    if (!plan) return;
    setBusy(id + "-delete");
    try {
      // Prefer stored path; fall back to parsing the download URL for legacy records
      await deleteFloorPlan(id, plan.storage_path ?? plan.url);
      toast.success("Floor plan deleted");
    } catch {
      toast.error("Delete failed. Please try again.");
    } finally {
      setBusy(null);
      setConfirmDelete(null);
    }
  };

  return (
    <>
      {lightbox && (
        <Lightbox src={lightbox.src} alt={lightbox.alt} onClose={() => setLightbox(null)} />
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {plans.map((plan) => {
          const isPdf = plan.url.toLowerCase().includes(".pdf") || plan.name.toLowerCase().endsWith(".pdf");
          const typeLabel = getTypeLabel(plan.url, plan.name);
          const isActivating = busy === plan.floor_plan_id + "-activate";
          const isScaling = busy === plan.floor_plan_id + "-scale";
          const isDeleting = busy === plan.floor_plan_id + "-delete";
          const awaitingConfirm = confirmDelete === plan.floor_plan_id;

          const handleThumbnailClick = () => {
            if (isPdf) {
              window.open(plan.url, "_blank");
            } else {
              setLightbox({ src: plan.url, alt: plan.name });
            }
          };

          return (
            <div key={plan.floor_plan_id} className="bg-s-surface border border-s-border rounded-xl overflow-hidden flex flex-col">
              {/* Thumbnail */}
              <div
                className="relative h-40 bg-s-elevated border-b border-s-border overflow-hidden cursor-pointer group"
                onClick={handleThumbnailClick}
                title={isPdf ? "Open PDF in new tab" : "View full size"}
              >
                {isPdf ? (
                  <>
                    <PdfThumbnail name={plan.name} />
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
                    <span className="absolute bottom-2 right-2 font-mono text-[9px] px-2 py-0.5 rounded-full bg-s-elevated/90 text-s-muted border border-s-border tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">
                      OPEN PDF ↗
                    </span>
                  </>
                ) : (
                  <>
                    <img
                      src={plan.url}
                      alt={plan.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display = "none";
                        const fb = e.currentTarget.parentElement?.querySelector("[data-fallback]") as HTMLElement | null;
                        if (fb) fb.style.display = "flex";
                      }}
                    />
                    {/* Fallback — shown via onError */}
                    <div
                      data-fallback
                      className="absolute inset-0 hidden items-center justify-center bg-s-elevated text-s-muted"
                    >
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/>
                        <line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/>
                      </svg>
                    </div>
                    {/* Hover overlay */}
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                      <svg className="text-white opacity-0 group-hover:opacity-100 transition-opacity drop-shadow" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                        <line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>
                      </svg>
                    </div>
                  </>
                )}

                {/* ACTIVE badge */}
                {plan.is_active && (
                  <span className="absolute top-2 right-2 font-mono text-[9px] px-2 py-0.5 rounded-full bg-s-success/90 text-white tracking-widest shadow-sm">
                    ACTIVE
                  </span>
                )}
              </div>

              {/* Info */}
              <div className="p-4 flex flex-col gap-3 flex-1">
                <div>
                  <p className="text-sm font-semibold text-s-text truncate">{plan.name}</p>
                  <p className="font-mono text-[10px] text-s-muted tracking-wide mt-0.5">
                    {typeLabel} · Uploaded {new Date(plan.uploaded_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                  </p>
                  <p className="font-mono text-[10px] text-s-muted tracking-wide">
                    Scale: {plan.scale_pixels_per_meter ? `${plan.scale_pixels_per_meter} px/m` : "Not calibrated"}
                  </p>
                </div>

                {isAdmin && (
                  <div className="space-y-2 mt-auto">
                    {/* Calibration input */}
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min="0.1"
                        step="0.1"
                        placeholder={plan.scale_pixels_per_meter ? String(plan.scale_pixels_per_meter) : "px per metre"}
                        value={scaleInputs[plan.floor_plan_id] ?? ""}
                        onChange={(e) => setScaleInputs((prev) => ({ ...prev, [plan.floor_plan_id]: e.target.value }))}
                        className="flex-1 bg-s-elevated border border-s-border rounded-lg px-2 py-1.5 text-xs text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors min-w-0"
                      />
                      <button
                        onClick={() => handleScaleSave(plan.floor_plan_id)}
                        disabled={isScaling || !scaleInputs[plan.floor_plan_id]}
                        className="px-2.5 py-1.5 rounded-lg bg-s-elevated border border-s-border text-xs text-s-muted hover:text-s-text hover:border-s-accent transition-colors disabled:opacity-40 shrink-0"
                      >
                        {isScaling ? "…" : "Calibrate"}
                      </button>
                    </div>

                    {/* Action row */}
                    <div className="flex gap-2">
                      {!plan.is_active && (
                        <button
                          onClick={() => handleActivate(plan.floor_plan_id)}
                          disabled={isActivating}
                          className="flex-1 py-1.5 rounded-lg bg-s-accent/15 text-s-accent font-mono text-[10px] hover:bg-s-accent/25 transition-colors disabled:opacity-40 tracking-widest"
                        >
                          {isActivating ? "…" : "SET ACTIVE"}
                        </button>
                      )}

                      {!awaitingConfirm ? (
                        <button
                          onClick={() => setConfirmDelete(plan.floor_plan_id)}
                          className="py-1.5 px-2.5 rounded-lg border border-s-border text-s-muted hover:border-s-danger hover:text-s-danger transition-colors"
                          title="Delete floor plan"
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                            <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
                          </svg>
                        </button>
                      ) : (
                        <div className="flex gap-1 flex-1">
                          <button
                            onClick={() => handleDelete(plan.floor_plan_id)}
                            disabled={isDeleting}
                            className="flex-1 py-1.5 rounded-lg bg-s-danger/20 text-s-danger font-mono text-[10px] hover:bg-s-danger/30 transition-colors disabled:opacity-40 tracking-widest"
                          >
                            {isDeleting ? "…" : "CONFIRM"}
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            className="py-1.5 px-2.5 rounded-lg border border-s-border text-s-muted hover:text-s-text transition-colors font-mono text-[10px]"
                          >
                            NO
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
