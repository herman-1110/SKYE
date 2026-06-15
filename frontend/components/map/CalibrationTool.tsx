"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { updateFloorScale } from "@/services/floorService";
import { toast } from "@/store/toastStore";
import type { FloorRecord } from "@/types/floor";

// Points stored as fractions (0.0–1.0) of the natural image dimensions.
// Independent of how the canvas is displayed — zoom/pan/resize safe.
interface Point { px: number; py: number; }

interface Props {
  buildingId: string;
  floor: FloorRecord;
  onClose: () => void;
  onCalibrated?: (scale: number) => void;
}

export default function CalibrationTool({ buildingId, floor, onClose, onCalibrated }: Props) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [pointA, setPointA] = useState<Point | null>(null);
  const [pointB, setPointB] = useState<Point | null>(null);
  const [cursorPos, setCursorPos] = useState<Point | null>(null);
  const [realDistance, setRealDistance] = useState("");
  const [saving, setSaving] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  // CSS-pixel bounds of the rendered image inside the canvas (objectFit: contain adds letterbox).
  // Used to position DOM marker overlays precisely over the visible image.
  const [imgArea, setImgArea] = useState({ x: 0, y: 0, w: 0, h: 0 });
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);

  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const imgRef       = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const panStart     = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);

  const clampPan = (x: number, y: number, z: number): { x: number; y: number } => {
    const container = containerRef.current;
    if (!container) return { x, y };
    const maxX = (container.offsetWidth  * (z - 1)) / 2;
    const maxY = (container.offsetHeight * (z - 1)) / 2;
    return {
      x: Math.max(-maxX, Math.min(maxX, x)),
      y: Math.max(-maxY, Math.min(maxY, y)),
    };
  };

  // Escape → close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Redraw canvas whenever any visual state changes
  useEffect(() => {
    const canvas = canvasRef.current;
    const img    = imgRef.current;
    if (!imgLoaded || !canvas || !img) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Set canvas bitmap to natural image size (clears existing bitmap)
    canvas.width  = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const W = canvas.width;
    const H = canvas.height;

    ctx.clearRect(0, 0, W, H);
    ctx.drawImage(img, 0, 0);

    const lw = Math.max(2, W / 600);

    // Rubber-band line while placing B
    if (step === 2 && pointA && cursorPos) {
      ctx.beginPath();
      ctx.moveTo(pointA.px * W, pointA.py * H);
      ctx.lineTo(cursorPos.px * W, cursorPos.py * H);
      ctx.strokeStyle = "rgba(245,158,11,0.55)";
      ctx.lineWidth = lw;
      ctx.setLineDash([6, 5]);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Committed A→B measurement line
    if (pointA && pointB) {
      ctx.beginPath();
      ctx.moveTo(pointA.px * W, pointA.py * H);
      ctx.lineTo(pointB.px * W, pointB.py * H);
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = lw * 1.3;
      ctx.setLineDash([8, 5]);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    // Markers are DOM overlays — see <div> below the canvas element
  }, [imgLoaded, pointA, pointB, cursorPos, step]);

  // Recompute the CSS-pixel rectangle that the image actually occupies inside
  // the canvas element (objectFit: contain may add letterbox bars).
  // Runs once on image load, then again on every window resize.
  useEffect(() => {
    if (!imgLoaded) return;
    const compute = () => {
      const canvas = canvasRef.current;
      if (!canvas || canvas.width === 0 || canvas.height === 0) return;
      // Use offsetWidth/Height (layout space, unaffected by CSS transform) so the
      // marker overlay's absolute position stays correct at any zoom level.
      const w = canvas.offsetWidth;
      const h = canvas.offsetHeight;
      const scale = Math.min(w / canvas.width, h / canvas.height);
      setImgArea({
        x: (w - canvas.width  * scale) / 2,
        y: (h - canvas.height * scale) / 2,
        w: canvas.width  * scale,
        h: canvas.height * scale,
      });
    };
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, [imgLoaded]);

  useEffect(() => {
    if (zoom <= 1) {
      setPan({ x: 0, y: 0 });
    } else {
      setPan((p) => clampPan(p.x, p.y, zoom));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom]);

  // Non-passive wheel listener so we can call preventDefault() and prevent page scroll.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.15 : -0.15;
      setZoom((z) => Math.max(1, Math.min(6, z + delta)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Convert CSS pointer coordinates → image fractions (0..1).
  // Accounts for the objectFit: contain letterbox offset.
  const toFraction = (e: React.MouseEvent<HTMLCanvasElement>): Point | null => {
    const canvas = canvasRef.current;
    if (!canvas || canvas.width === 0 || canvas.height === 0) return null;
    const rect  = canvas.getBoundingClientRect();
    const scale = Math.min(rect.width / canvas.width, rect.height / canvas.height);
    const rendW = canvas.width  * scale;
    const rendH = canvas.height * scale;
    const offX  = (rect.width  - rendW) / 2;
    const offY  = (rect.height - rendH) / 2;
    const relX  = e.clientX - rect.left - offX;
    const relY  = e.clientY - rect.top  - offY;
    if (relX < 0 || relY < 0 || relX > rendW || relY > rendH) return null;
    return {
      px: Math.max(0, Math.min(1, relX / rendW)),
      py: Math.max(0, Math.min(1, relY / rendH)),
    };
  };

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (step >= 3 || !imgLoaded) return;
    const pt = toFraction(e);
    if (!pt) return;
    if (step === 1) { setPointA(pt); setStep(2); }
    else            { setPointB(pt); setStep(3); setCursorPos(null); }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (step !== 2) return;
    setCursorPos(toFraction(e));
  };

  const handleRedo = () => {
    // Only reset calibration points — does NOT touch floor.url or imgLoaded
    setStep(1); setPointA(null); setPointB(null); setCursorPos(null); setRealDistance("");
  };

  // Natural-pixel distance — independent of display scale, used for px/m calculation
  const pixelDistance = (() => {
    if (!pointA || !pointB || !imgRef.current) return 0;
    const img = imgRef.current;
    const ax = pointA.px * img.naturalWidth,  ay = pointA.py * img.naturalHeight;
    const bx = pointB.px * img.naturalWidth,  by = pointB.py * img.naturalHeight;
    return Math.sqrt((bx - ax) ** 2 + (by - ay) ** 2);
  })();

  const parsedDist = parseFloat(realDistance);
  const calculatedScale =
    realDistance && parsedDist > 0 && pixelDistance > 0
      ? pixelDistance / parsedDist
      : null;

  const handleSave = async () => {
    if (!calculatedScale || calculatedScale <= 0) return;
    setSaving(true);
    try {
      const rounded = Math.round(calculatedScale * 100) / 100;
      await updateFloorScale(buildingId, floor.id, rounded);
      toast.success(`Floor calibrated: ${calculatedScale.toFixed(1)} px/m`);
      onCalibrated?.(calculatedScale);
      onClose();
    } catch {
      toast.error("Calibration save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const stepLabel =
    step === 1 ? "Click the FIRST point on the floor plan" :
    step === 2 ? "Click the SECOND point" :
    "Enter the real-world distance";

  return createPortal(
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        backgroundColor: "rgba(0,0,0,0.78)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {/* Hidden img — preloads the floor plan before the canvas draws */}
      <img
        ref={imgRef}
        src={floor.url}
        alt=""
        style={{ display: "none" }}
        onLoad={() => setImgLoaded(true)}
      />

      {/* Step hint pill */}
      {step < 3 && imgLoaded && (
        <div
          className="absolute top-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-2 rounded-full pointer-events-none z-50 border border-white/20"
          style={{ background: "rgba(255,255,255,0.25)", backdropFilter: "blur(8px)", whiteSpace: "nowrap" }}
        >
          <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse shrink-0" />
          <span className="font-mono text-[11px] text-s-text">{stepLabel}</span>
        </div>
      )}

      {/* ── Modal box ──────────────────────────────────────────────── */}
      <div
        style={{
          position: "relative",
          display: "flex",
          width: "92vw",
          maxWidth: 1300,
          height: "88vh",
          background: "var(--bg-surface)",
          borderRadius: 14,
          overflow: "hidden",
          border: "1px solid var(--border)",
          boxShadow: "0 24px 64px rgba(0,0,0,0.55)",
        }}
      >
        {/* ✕ Close — absolute inside modal box, always above canvas and panel */}
        <button
          onClick={onClose}
          aria-label="Close calibration"
          className="absolute top-3 right-3 z-10 flex items-center justify-center w-8 h-8 rounded-lg bg-transparent text-s-muted hover:text-s-text transition-colors"
          style={{ fontSize: 15 }}
        >
          ✕
        </button>

        {/* ── LEFT: canvas area ─────────────────────────────────────── */}
        <div
          style={{
            flex: 1,
            position: "relative",
            overflow: "hidden",
            background: "#060608",
          }}
        >
          {!imgLoaded && (
            <div className="absolute inset-0 flex items-center justify-center font-mono text-xs text-white/30 tracking-wide">
              Loading floor plan…
            </div>
          )}

          {/* Zoom controls */}
          {imgLoaded && (
            <div
              style={{
                position: "absolute",
                bottom: 12,
                right: 12,
                zIndex: 20,
                display: "flex",
                gap: 6,
                alignItems: "center",
              }}
            >
              <button
                onClick={() => setZoom((z) => Math.max(1, z - 0.25))}
                style={{
                  width: 28, height: 28, borderRadius: 7, border: "1px solid var(--border)",
                  background: "var(--bg-elevated)", color: "var(--text-primary)",
                  fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: "pointer", lineHeight: 1,
                }}
                title="Zoom out"
              >−</button>
              <span style={{ fontFamily: "IBM Plex Mono, monospace", fontSize: 10, color: "var(--text-secondary)", minWidth: 36, textAlign: "center" }}>
                {Math.round(zoom * 100)}%
              </span>
              <button
                onClick={() => setZoom((z) => Math.min(6, z + 0.25))}
                style={{
                  width: 28, height: 28, borderRadius: 7, border: "1px solid var(--border)",
                  background: "var(--bg-elevated)", color: "var(--text-primary)",
                  fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: "pointer", lineHeight: 1,
                }}
                title="Zoom in"
              >+</button>
              {zoom > 1 && (
                <button
                  onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}
                  style={{
                    height: 28, padding: "0 10px", borderRadius: 7, border: "1px solid var(--border)",
                    background: "var(--bg-elevated)", color: "var(--text-secondary)",
                    fontSize: 10, fontFamily: "IBM Plex Mono, monospace", cursor: "pointer",
                  }}
                  title="Reset zoom"
                >Reset</button>
              )}
            </div>
          )}

          {/* Pan/zoom container — intercepts wheel (via useEffect) and drag-to-pan */}
          <div
            ref={containerRef}
            style={{
              position: "absolute",
              inset: 0,
              overflow: "hidden",
              cursor: isPanning ? "grabbing" : (step < 3 && imgLoaded ? "crosshair" : zoom > 1 ? "grab" : "default"),
            }}
            onMouseDown={(e) => {
              if (zoom <= 1) return;
              setIsPanning(true);
              panStart.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y };
            }}
            onMouseMove={(e) => {
              if (isPanning && panStart.current) {
                setPan(clampPan(
                  panStart.current.px + (e.clientX - panStart.current.mx),
                  panStart.current.py + (e.clientY - panStart.current.my),
                  zoom,
                ));
              }
            }}
            onMouseUp={() => { setIsPanning(false); panStart.current = null; }}
            onMouseLeave={() => {
              setIsPanning(false);
              panStart.current = null;
              if (step === 2) setCursorPos(null);
            }}
          >
            {/* Transform wrapper — canvas + overlay move together so markers stay aligned */}
            <div
              style={{
                width: "100%",
                height: "100%",
                position: "relative",
                transformOrigin: "center center",
                transform: `scale(${zoom}) translate(${pan.x / zoom}px, ${pan.y / zoom}px)`,
                transition: isPanning ? "none" : "transform 0.1s ease",
              }}
            >
              <canvas
                ref={canvasRef}
                onClick={handleCanvasClick}
                onMouseMove={handleCanvasMouseMove}
                style={{
                  display: imgLoaded ? "block" : "none",
                  width: "100%",
                  height: "100%",
                  objectFit: "contain",
                  cursor: "inherit",
                }}
              />

              {/* ── DOM marker overlay ───────────────────────────────────
                   imgArea is computed in layout space (offsetWidth/Height), so
                   these positions are correct inside the transform wrapper. */}
              {imgLoaded && imgArea.w > 0 && (
                <div
                  style={{
                    position: "absolute",
                    left: imgArea.x,
                    top: imgArea.y,
                    width: imgArea.w,
                    height: imgArea.h,
                    pointerEvents: "none",
                  }}
                >
                  {([{ pt: pointA, label: "A" }, { pt: pointB, label: "B" }] as const).map(
                    ({ pt, label }) =>
                      pt && (
                        <div
                          key={label}
                          style={{
                            position: "absolute",
                            left: `${pt.px * 100}%`,
                            top: `${pt.py * 100}%`,
                            transform: "translate(-50%, -50%)",
                            pointerEvents: "none",
                          }}
                        >
                          {/* Label sits above the ring, no background pill */}
                          <div
                            style={{
                              position: "absolute",
                              top: "-18px",
                              left: "50%",
                              transform: "translateX(-50%)",
                              fontSize: "10px",
                              fontFamily: "IBM Plex Mono, monospace",
                              color: "var(--accent)",
                              whiteSpace: "nowrap",
                              userSelect: "none",
                            }}
                          >
                            {label}
                          </div>

                          {/* Outer ring — hover scales up */}
                          <div
                            style={{
                              width: "20px",
                              height: "20px",
                              borderRadius: "50%",
                              border: "1.5px solid rgba(245,158,11,0.6)",
                              boxShadow: "0 0 0 3px rgba(245,158,11,0.2)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              transition: "transform 120ms ease",
                              pointerEvents: "auto",
                              cursor: "default",
                            }}
                            onMouseEnter={(e) => {
                              (e.currentTarget as HTMLDivElement).style.transform = "scale(1.2)";
                            }}
                            onMouseLeave={(e) => {
                              (e.currentTarget as HTMLDivElement).style.transform = "scale(1)";
                            }}
                          >
                            {/* Inner dot */}
                            <div
                              style={{
                                width: "6px",
                                height: "6px",
                                borderRadius: "50%",
                                backgroundColor: "var(--accent)",
                              }}
                            />
                          </div>
                        </div>
                      )
                  )}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── RIGHT: controls panel ─────────────────────────────────── */}
        <div
          style={{
            width: 280,
            flexShrink: 0,
            background: "var(--bg-elevated)",
            borderLeft: "1px solid var(--border)",
            padding: "48px 20px 20px",
            display: "flex",
            flexDirection: "column",
            gap: 20,
            overflowY: "auto",
          }}
        >
          {/* Title */}
          <div>
            <p className="font-mono text-[9px] text-s-muted tracking-widest uppercase mb-1">
              {floor.name}
            </p>
            <h3 className="text-sm font-semibold text-s-text">Floor Calibration</h3>
            <p className="text-xs text-s-muted mt-1 leading-relaxed">{stepLabel}</p>
          </div>

          {/* Step indicators */}
          <div className="flex flex-col gap-2.5">
            {([1, 2, 3] as const).map((s) => (
              <div
                key={s}
                className="flex items-center gap-2.5"
                style={{ opacity: step === s ? 1 : step > s ? 0.55 : 0.3 }}
              >
                <div
                  className="w-5 h-5 rounded-full shrink-0 flex items-center justify-center text-[9px] font-mono font-bold"
                  style={{
                    background: step > s ? "#10b981" : step === s ? "#f59e0b" : "var(--bg-surface)",
                    border: `2px solid ${step > s ? "#10b981" : step === s ? "#f59e0b" : "var(--border)"}`,
                    color: step >= s ? "#000" : "var(--text-secondary)",
                  }}
                >
                  {step > s ? "✓" : s}
                </div>
                <span className="text-[11px] font-mono text-s-text">
                  {s === 1 ? "Place point A" : s === 2 ? "Place point B" : "Enter distance"}
                </span>
              </div>
            ))}
          </div>

          {/* Step 3: distance input */}
          {step === 3 && (
            <div className="flex flex-col gap-3 pt-1">
              <div>
                <p className="font-mono text-[9px] text-s-muted tracking-widest uppercase mb-1">Pixel distance</p>
                <p className="font-mono text-sm font-bold text-s-text">{pixelDistance.toFixed(0)} px</p>
              </div>

              <div>
                <p className="font-mono text-[9px] text-s-muted tracking-widest uppercase mb-1.5">Real-world distance</p>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="1"
                    step="1"
                    placeholder="e.g. 10"
                    value={realDistance}
                    onChange={(e) => setRealDistance(e.target.value)}
                    onWheel={(e) => {
                      e.preventDefault();
                      const current = parseFloat(realDistance) || 0;
                      setRealDistance(String(Math.max(1, e.deltaY < 0 ? current + 1 : current - 1)));
                    }}
                    autoFocus
                    className="flex-1 bg-s-surface border border-s-border rounded-lg px-3 py-1.5 text-sm font-mono text-s-text placeholder:text-s-muted focus:outline-none focus:border-s-accent transition-colors"
                  />
                  <span className="font-mono text-[11px] text-s-muted">m</span>
                </div>
              </div>

              <div>
                <p className="font-mono text-[9px] text-s-muted tracking-widest uppercase mb-1">Scale</p>
                <p
                  className="font-mono text-sm font-bold"
                  style={{ color: calculatedScale ? "#f59e0b" : "var(--text-secondary)" }}
                >
                  {calculatedScale ? `${calculatedScale.toFixed(2)} px/m` : "— px/m"}
                </p>
              </div>
            </div>
          )}

          {/* Spacer pushes buttons to bottom */}
          <div style={{ flex: 1 }} />

          {/* Action buttons */}
          <div className="flex flex-col gap-2">
            {step > 1 && (
              <button
                onClick={handleRedo}
                className="py-2 px-4 rounded-lg border border-s-border text-[11px] font-mono text-s-muted hover:text-s-text transition-colors"
              >
                ← Reset Points
              </button>
            )}
            {step === 3 && (
              <button
                onClick={handleSave}
                disabled={saving || !calculatedScale || parsedDist <= 0}
                className="py-2.5 px-4 rounded-lg font-bold text-xs hover:opacity-90 disabled:opacity-40 transition-opacity flex items-center justify-center gap-1.5"
                style={{ background: "#f59e0b", color: "#000" }}
              >
                {saving && (
                  <span className="h-3 w-3 rounded-full border-2 border-black border-t-transparent animate-spin" />
                )}
                {saving ? "Saving…" : "✓ Save Calibration"}
              </button>
            )}


          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
