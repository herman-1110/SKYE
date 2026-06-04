"use client";
import { useCriticalAlertStore } from "@/store/criticalAlertStore";

const ALERT_LABELS: Record<string, string> = {
  man_down:  "MAN DOWN",
  collision: "COLLISION WARNING",
};

const ALERT_DESCRIPTIONS: Record<string, string> = {
  man_down:  "Personnel stationary — possible injury detected",
  collision: "Predicted collision between personnel and forklift",
};

function WarningIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  );
}

function XIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 12 12" fill="none"
      stroke="currentColor" strokeWidth="2.5"
      strokeLinecap="round" strokeLinejoin="round">
      <line x1="2" y1="2" x2="10" y2="10"/>
      <line x1="10" y1="2" x2="2" y2="10"/>
    </svg>
  );
}

export default function CriticalAlertBanner() {
  const queue = useCriticalAlertStore((s) => s.queue);
  const dismissCritical = useCriticalAlertStore((s) => s.dismissCritical);

  if (queue.length === 0) return null;

  return (
    <div className="fixed top-16 left-1/2 -translate-x-1/2 z-[9999] flex flex-col gap-2 w-full max-w-lg px-4 pointer-events-none">
      {queue.map((alert) => (
        <div
          key={alert.alert_id}
          className="pointer-events-auto rounded-xl px-4 py-3.5 flex items-start gap-3 animate-toast-in"
          style={{
            background: "rgba(220, 38, 38, 0.12)",
            border: "1.5px solid rgba(220, 38, 38, 0.6)",
            boxShadow: "0 0 24px rgba(220, 38, 38, 0.25), 0 4px 16px rgba(0,0,0,0.4)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
          }}
        >
          {/* Pulsing icon */}
          <span className="shrink-0 text-red-400 mt-0.5 animate-amber-pulse">
            <WarningIcon />
          </span>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-xs font-bold text-red-400 tracking-widest">
                {ALERT_LABELS[alert.alert_type] ?? alert.alert_type.toUpperCase()}
              </span>
              <span className="font-mono text-[10px] text-red-400/60">
                {alert.timestamp.slice(11, 19)} UTC
              </span>
            </div>
            <p className="text-xs text-s-muted mb-1.5">
              {ALERT_DESCRIPTIONS[alert.alert_type]}
            </p>
            {/* Persons involved */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="font-mono text-xs text-s-text bg-s-elevated border border-s-border px-2 py-0.5 rounded-md">
                {alert.person_id}
              </span>
              {alert.alert_type === "collision" && alert.other_person_id && (
                <>
                  <span className="text-red-400 text-xs font-bold">↔</span>
                  <span className="font-mono text-xs text-s-text bg-s-elevated border border-s-border px-2 py-0.5 rounded-md">
                    {alert.other_person_id}
                  </span>
                </>
              )}
            </div>
            {/* Zone */}
            {alert.zone && (
              <p className="font-mono text-[10px] text-s-muted mt-1.5">
                Zone: {alert.zone}
              </p>
            )}
          </div>

          {/* Dismiss */}
          <button
            onClick={() => dismissCritical(alert.alert_id)}
            className="shrink-0 text-s-muted hover:text-red-400 transition-colors mt-0.5"
            aria-label="Dismiss critical alert"
          >
            <XIcon />
          </button>
        </div>
      ))}
    </div>
  );
}
