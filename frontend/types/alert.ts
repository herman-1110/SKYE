export type AlertType =
  | "man_down"
  | "collision"
  | "ghost_patrol"
  | "patrol_violation";

export type FeedbackValue = "confirmed" | "fixed" | "false_alarm";

export interface AlertRecord {
  alert_id: string;
  alert_type: AlertType;
  person_id: string;
  zone: string;
  timestamp: string;         // ISO 8601
  resolved: boolean;
  feedback: FeedbackValue | null;
  feedback_reason: string | null;
  feedback_timestamp: string | null;
}
