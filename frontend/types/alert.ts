export type AlertType =
  | "man_down"
  | "collision"
  | "ghost_patrol"
  | "patrol_violation";

// FeedbackValue stays here — used by FeedbackForm and alertService
export type FeedbackValue = "confirmed" | "fixed" | "false_alarm";

export interface AlertRecord {
  alert_id: string;
  alert_type: AlertType;
  person_id: string;
  zone: string;
  timestamp: string;    // ISO 8601
  resolved: boolean;
  other_person_id?: string;   // collision only: the other party
}
