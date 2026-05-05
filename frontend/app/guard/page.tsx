"use client";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { getMyPosition, getMyPatrol } from "@/services/guardService";
import type { PositionRecord } from "@/types/position";

interface PatrolEntry {
  checkpoint_name: string;
  expected_arrival: string;
  actual_arrival: string | null;
  compliant: boolean;
  dwell_time_seconds: number;
}

export default function GuardPage() {
  const { user } = useAuth();
  const [position, setPosition] = useState<PositionRecord | null>(null);
  const [patrol, setPatrol] = useState<PatrolEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    user.getIdToken().then(async (token) => {
      const [pos, pat] = await Promise.all([getMyPosition(token), getMyPatrol(token)]);
      setPosition(pos);
      setPatrol(pat as PatrolEntry[]);
      setLoading(false);
    });
  }, [user]);

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <span className="h-6 w-6 rounded-full border-2 border-s-accent border-t-transparent animate-spin" />
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <h1 className="font-mono text-xs text-s-muted tracking-widest uppercase">My Status</h1>

      {/* Position card */}
      <div className="bg-s-surface border border-s-border rounded-lg p-4 space-y-3">
        <p className="font-mono text-xs text-s-accent tracking-widest uppercase">Live Position</p>
        {position ? (
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "Zone", value: position.zone },
              { label: "Person ID", value: position.person_id },
              { label: "X (m)", value: position.x?.toFixed(2) ?? "—" },
              { label: "Y (m)", value: position.y?.toFixed(2) ?? "—" },
              { label: "Stationary", value: position.is_stationary ? "Yes" : "No" },
              { label: "Last Update", value: position.timestamp?.slice(11, 19) ?? "—" },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="font-mono text-[10px] text-s-muted uppercase tracking-widest">{label}</p>
                <p className="font-mono text-sm text-s-text">{value}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-s-muted text-sm">No position data yet.</p>
        )}
      </div>

      {/* Patrol log */}
      <div className="bg-s-surface border border-s-border rounded-lg p-4 space-y-3">
        <p className="font-mono text-xs text-s-accent tracking-widest uppercase">
          Patrol Log ({patrol.length} checkpoints)
        </p>
        {patrol.length === 0 ? (
          <p className="text-s-muted text-sm">No patrol entries for this shift.</p>
        ) : (
          <div className="space-y-2">
            {patrol.map((entry, i) => (
              <div
                key={i}
                className={`rounded-lg border p-3 ${
                  entry.compliant ? "border-s-success/40 bg-s-success/5" : "border-s-danger/40 bg-s-danger/5"
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="font-mono text-xs text-s-text">{entry.checkpoint_name}</p>
                  <span
                    className={`font-mono text-[10px] px-2 py-0.5 rounded-full ${
                      entry.compliant
                        ? "bg-s-success/20 text-s-success"
                        : "bg-s-danger/20 text-s-danger"
                    }`}
                  >
                    {entry.compliant ? "COMPLIANT" : "VIOLATION"}
                  </span>
                </div>
                <p className="font-mono text-[10px] text-s-muted mt-1">
                  Expected {entry.expected_arrival?.slice(11, 19) ?? "—"} ·{" "}
                  Arrived {entry.actual_arrival?.slice(11, 19) ?? "—"} ·{" "}
                  Dwell {entry.dwell_time_seconds}s
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
