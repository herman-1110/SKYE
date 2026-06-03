"use client";
import { useEffect, useState } from "react";
import { simulationService, type SimMode, type SimStatus } from "@/services/simulationService";
import { toast } from "@/store/toastStore";

export default function SimulationControls() {
  const [status, setStatus] = useState<SimStatus>({ running: false, mode: null });
  const [loading, setLoading] = useState<SimMode | "stop" | null>(null);

  const refresh = async () => {
    try {
      const s = await simulationService.status();
      setStatus(s);
    } catch {
      // silently ignore — backend may not be running
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5_000);
    return () => clearInterval(id);
  }, []);

  const start = async (mode: SimMode) => {
    setLoading(mode);
    try {
      await simulationService.start(mode);
      setStatus({ running: true, mode });
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to start simulation");
    } finally {
      setLoading(null);
    }
  };

  const stop = async () => {
    setLoading("stop");
    try {
      await simulationService.stop();
      setStatus({ running: false, mode: null });
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to stop simulation");
    } finally {
      setLoading(null);
    }
  };

  const busy = loading !== null;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="font-mono text-[10px] text-s-muted tracking-widest uppercase shrink-0">
        Simulation
      </span>

      {/* Status badge */}
      <span
        className="font-mono text-[10px] tracking-widest px-2 py-0.5 rounded-full border"
        style={{
          color:            status.running ? "var(--accent)"       : "var(--text-muted)",
          borderColor:      status.running ? "var(--accent)"       : "var(--border)",
          backgroundColor:  status.running ? "rgba(var(--accent-rgb, 245 158 11) / 0.10)" : "transparent",
        }}
      >
        {status.running ? `RUNNING · ${status.mode?.toUpperCase()}` : "STOPPED"}
      </span>

      {/* Start buttons — hidden while running */}
      {!status.running && (
        <>
          <button
            disabled={busy}
            onClick={() => start("patrol")}
            className="font-mono text-[10px] tracking-widest px-2.5 py-1.5 rounded-lg border transition-colors"
            style={{
              borderColor:     "var(--border)",
              color:           "var(--text-secondary)",
              backgroundColor: "var(--bg-elevated)",
              opacity: busy ? 0.5 : 1,
              cursor: busy ? "not-allowed" : "pointer",
            }}
          >
            {loading === "patrol" ? "Starting…" : "Patrol"}
          </button>

          <button
            disabled={busy}
            onClick={() => start("events")}
            className="font-mono text-[10px] tracking-widest px-2.5 py-1.5 rounded-lg border transition-colors"
            style={{
              borderColor:     "var(--accent)",
              color:           "var(--accent)",
              backgroundColor: "rgba(var(--accent-rgb, 245 158 11) / 0.08)",
              opacity: busy ? 0.5 : 1,
              cursor: busy ? "not-allowed" : "pointer",
            }}
          >
            {loading === "events" ? "Starting…" : "Events"}
          </button>
        </>
      )}

      {/* Stop button — shown while running */}
      {status.running && (
        <button
          disabled={busy}
          onClick={stop}
          className="font-mono text-[10px] tracking-widest px-2.5 py-1.5 rounded-lg border transition-colors"
          style={{
            borderColor:     "var(--danger, #ef4444)",
            color:           "var(--danger, #ef4444)",
            backgroundColor: "rgba(239 68 68 / 0.08)",
            opacity: busy ? 0.5 : 1,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          {loading === "stop" ? "Stopping…" : "Stop"}
        </button>
      )}
    </div>
  );
}
