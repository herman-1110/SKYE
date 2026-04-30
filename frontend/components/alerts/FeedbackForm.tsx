"use client";
import { useState } from "react";
import type { AlertRecord, FeedbackValue } from "@/types/alert";
import { submitFeedback } from "@/services/alertService";

interface Props {
  alert: AlertRecord;
  onSubmitted: () => void;
}

const OPTIONS: { value: FeedbackValue; label: string }[] = [
  { value: "confirmed",   label: "Confirmed — real incident" },
  { value: "fixed",       label: "Fixed — resolved on-site" },
  { value: "false_alarm", label: "False Alarm" },
];

export default function FeedbackForm({ alert, onSubmitted }: Props) {
  const [selected, setSelected] = useState<FeedbackValue>("confirmed");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await submitFeedback(alert.alert_id, selected, reason);
      onSubmitted();
    } catch {
      setError("Submission failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-3">
      <fieldset>
        <legend className="text-sm font-medium mb-2">Feedback</legend>
        <div className="space-y-1">
          {OPTIONS.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="radio"
                name="feedback"
                value={opt.value}
                checked={selected === opt.value}
                onChange={() => setSelected(opt.value)}
              />
              {opt.label}
            </label>
          ))}
        </div>
      </fieldset>
      <textarea
        className="w-full border rounded p-2 text-sm resize-none"
        placeholder="Optional reason..."
        rows={2}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      {error && <p className="text-red-500 text-xs">{error}</p>}
      <button
        onClick={handleSubmit}
        disabled={submitting}
        className="bg-blue-600 text-white rounded px-4 py-1.5 text-sm disabled:opacity-50"
      >
        {submitting ? "Submitting…" : "Submit Feedback"}
      </button>
    </div>
  );
}
