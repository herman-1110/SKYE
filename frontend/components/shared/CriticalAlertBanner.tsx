"use client";
import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { useCriticalQueue } from "@/hooks/useAlerts";
import { acknowledgeAlert } from "@/services/alertService";
import { useCriticalAlertStore } from "@/store/criticalAlertStore";
import { toast } from "@/store/toastStore";
import type { AlertRecord } from "@/types/alert";
import { isAdminRole } from "@/types/user";

const ALERT_LABELS: Record<string, string> = {
  man_down:  "MAN DOWN",
  collision: "COLLISION WARNING",
  possible_man_down:   "POSSIBLE MAN DOWN",
  positioning_offline: "POSITIONING OFFLINE",
};

const ALERT_DESCRIPTIONS: Record<string, string> = {
  man_down:  "Personnel stationary — possible injury detected",
  collision: "Predicted collision between personnel and forklift",
  possible_man_down:
    "Little or no movement, but only one or two APs can hear this person. Check on them.",
  positioning_offline:
    "No AP reports are reaching SKYE. Man-down and collision checks are paused until they return.",
};

// Amber variant for the alerts that need a look but aren't a confirmed
// emergency; red for the rest.
const AMBER_TYPES = new Set(["possible_man_down", "positioning_offline"]);

const RED_STYLE = {
  background: "rgba(220, 38, 38, 0.12)",
  border: "1.5px solid rgba(220, 38, 38, 0.6)",
  boxShadow: "0 0 24px rgba(220, 38, 38, 0.25), 0 4px 16px rgba(0,0,0,0.4)",
};

const AMBER_STYLE = {
  background: "rgba(245, 158, 11, 0.12)",
  border: "1.5px solid rgba(245, 158, 11, 0.6)",
  boxShadow: "0 0 24px rgba(245, 158, 11, 0.25), 0 4px 16px rgba(0,0,0,0.4)",
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

function reasonOf(err: unknown): string {
  return err instanceof Error && err.message ? err.message : "Something went wrong.";
}

export default function CriticalAlertBanner() {
  const queue = useCriticalQueue();
  const { userRecord } = useAuth();
  const isAdmin = isAdminRole(userRecord?.role);
  const pendingIds = useCriticalAlertStore((s) => s.pendingIds);
  const hide = useCriticalAlertStore((s) => s.hide);
  const setPending = useCriticalAlertStore((s) => s.setPending);
  const [dismissingAll, setDismissingAll] = useState(false);

  if (queue.length === 0) return null;

  // Admins and the owner: acknowledge it for everyone (D2.2). Throws on
  // failure, and the alert stays.
  async function acknowledge(alert: AlertRecord): Promise<void> {
    setPending(alert.alert_id, true);
    try {
      await acknowledgeAlert(alert.alert_id);
      hide(alert.alert_id); // the live data says so in every tab a moment later
    } finally {
      setPending(alert.alert_id, false);
    }
  }

  async function dismiss(alert: AlertRecord) {
    if (!isAdmin) {
      hide(alert.alert_id); // this tab only, until a reload (D2.3)
      return;
    }
    try {
      await acknowledge(alert);
    } catch (err) {
      toast.error(`Couldn't dismiss the alert for everyone: ${reasonOf(err)}`);
    }
  }

  // D2.5: each shown alert in turn; one toast if any failed.
  async function dismissAll() {
    const shown = queue.filter((a) => !pendingIds.has(a.alert_id));
    setDismissingAll(true);
    let failed = 0;
    let reason = "";
    for (const alert of shown) {
      try {
        await acknowledge(alert);
      } catch (err) {
        failed += 1;
        reason = reasonOf(err);
      }
    }
    setDismissingAll(false);
    if (failed > 0) {
      toast.error(`${failed} of ${shown.length} alerts couldn't be dismissed for everyone: ${reason}`);
    }
  }

  return (
    <div className="fixed top-16 left-1/2 -translate-x-1/2 z-[9999] flex flex-col gap-2 w-full max-w-lg px-4 pointer-events-none">
      {/* At the top, so it stays on screen when a backlog runs past the bottom */}
      {isAdmin && queue.length >= 2 && (
        <div className="flex justify-end">
          <button
            onClick={() => void dismissAll()}
            disabled={dismissingAll}
            className="pointer-events-auto px-3 py-1 rounded-md text-[11px] font-mono border border-s-border bg-s-surface text-s-text hover:bg-s-elevated transition-colors disabled:opacity-50"
            title="Close every pop-up below for everyone. The alerts stay active until someone gives feedback."
          >
            {dismissingAll ? "Dismissing…" : `Dismiss all (${queue.length})`}
          </button>
        </div>
      )}
      {queue.map((alert) => {
        const amber = AMBER_TYPES.has(alert.alert_type);
        const tone = amber ? "text-amber-400" : "text-red-400";
        const pending = pendingIds.has(alert.alert_id);
        return (
          <div
            key={alert.alert_id}
            className="pointer-events-auto rounded-xl px-4 py-3.5 flex items-start gap-3 animate-toast-in"
            style={{
              ...(amber ? AMBER_STYLE : RED_STYLE),
              backdropFilter: "blur(12px)",
              WebkitBackdropFilter: "blur(12px)",
            }}
          >
            {/* Pulsing icon */}
            <span className={`shrink-0 ${tone} mt-0.5 animate-amber-pulse`}>
              <WarningIcon />
            </span>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={`font-mono text-xs font-bold ${tone} tracking-widest`}>
                  {ALERT_LABELS[alert.alert_type] ?? alert.alert_type.toUpperCase()}
                </span>
                <span className={`font-mono text-[10px] ${amber ? "text-amber-400/60" : "text-red-400/60"}`}>
                  {alert.timestamp.slice(11, 19)} UTC
                </span>
              </div>
              <p className="text-xs text-s-muted mb-1.5">
                {ALERT_DESCRIPTIONS[alert.alert_type]}
              </p>
              {/* Persons involved (none for positioning_offline) */}
              {alert.person_id && (
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
              )}
              {/* Zone */}
              {alert.zone && (
                <p className="font-mono text-[10px] text-s-muted mt-1.5">
                  Zone: {alert.zone}
                </p>
              )}
            </div>

            {/* Dismiss */}
            <button
              onClick={() => void dismiss(alert)}
              disabled={pending}
              className={`shrink-0 text-s-muted ${amber ? "hover:text-amber-400" : "hover:text-red-400"} transition-colors mt-0.5 disabled:opacity-40`}
              title={isAdmin ? "Dismiss for everyone" : "Only an admin can dismiss this for everyone"}
              aria-label={isAdmin ? "Dismiss this alert for everyone" : "Hide this alert in this tab"}
            >
              <XIcon />
            </button>
          </div>
        );
      })}
    </div>
  );
}
