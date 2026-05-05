"use client";
import { useState } from "react";
import type { AlertRecord, FeedbackValue } from "@/types/alert";
import { submitFeedback } from "@/services/alertService";
import { toast } from "@/store/toastStore";
import AlertTypeBadge from "@/components/shared/AlertTypeBadge";

interface Props { alert: AlertRecord; onSubmitted: () => void }

const OPTIONS: { value: FeedbackValue; label: string; desc: string }[] = [
  { value: "confirmed",   label: "Confirmed Incident", desc: "Real safety event — escalate if needed" },
  { value: "fixed",       label: "Resolved On-site",   desc: "Issue addressed, no further action" },
  { value: "false_alarm", label: "False Alarm",         desc: "No actual incident occurred" },
];

export default function FeedbackForm({ alert, onSubmitted }: Props) {
  const [selected, setSelected] = useState<FeedbackValue>("confirmed");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await submitFeedback(alert.alert_id, selected, reason);
      toast.success("Feedback submitted — report updated");
      onSubmitted();
    } catch {
      toast.error("Submission failed. Check backend connection.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-full flex flex-col gap-4">
      {/* Alert header */}
      <div className="bg-s-surface rounded-lg border border-s-border p-4 space-y-2">
        <AlertTypeBadge type={alert.alert_type} />
        <div className="space-y-0.5">
          <p className="text-sm font-semibold text-s-text">{alert.person_id}</p>
          <p className="text-xs text-s-muted">{alert.zone}</p>
        </div>
        <div className="border-t border-s-border pt-2 space-y-1">
          <p className="font-mono text-[10px] text-s-mono">
            <span className="text-s-muted">DETECTED: </span>{alert.timestamp}
          </p>
          <p className="font-mono text-[10px] text-s-mono">
            <span className="text-s-muted">ALERT ID: </span>{alert.alert_id}
          </p>
        </div>
      </div>

      {/* Feedback options */}
      <fieldset className="space-y-2">
        <legend className="text-xs font-mono text-s-muted tracking-widest uppercase mb-2">Operator Response</legend>
        {OPTIONS.map((opt) => (
          <label
            key={opt.value}
            className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors
              ${selected === opt.value ? "border-s-accent bg-s-elevated" : "border-s-border bg-s-surface hover:bg-s-elevated"}`}
          >
            <input
              type="radio" name="feedback" value={opt.value}
              checked={selected === opt.value}
              onChange={() => setSelected(opt.value)}
              className="mt-0.5 accent-amber-500"
            />
            <div>
              <p className="text-sm font-medium text-s-text">{opt.label}</p>
              <p className="text-xs text-s-muted">{opt.desc}</p>
            </div>
          </label>
        ))}
      </fieldset>

      {/* Notes */}
      <textarea
        className="w-full bg-s-surface border border-s-border rounded-lg px-3 py-2 text-sm text-s-text placeholder:text-s-muted resize-none focus:outline-none focus:border-s-accent font-mono"
        placeholder="Optional notes for audit record…"
        rows={3}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />

      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="w-full py-2.5 rounded-lg bg-s-accent text-s-base font-semibold text-sm disabled:opacity-40 hover:opacity-90 transition-opacity flex items-center justify-center gap-2"
      >
        {submitting && <span className="h-4 w-4 rounded-full border-2 border-s-base border-t-transparent animate-spin" />}
        {submitting ? "Submitting…" : "Submit Feedback"}
      </button>
    </div>
  );
}
