export interface FeedbackRecord {
  feedback_id: string;
  alert_id: string;
  alert_type: string;
  zone: string;
  feedback: "confirmed" | "fixed" | "false_alarm";
  timestamp: string;          // ISO 8601
  feedback_reason: string | null;
  shift_id: string | null;
}
