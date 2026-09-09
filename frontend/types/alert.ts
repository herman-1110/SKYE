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
  // man_down: "stillness" | "signal_loss"
  // patrol_violation: "missed_checkpoint" | "short_dwell" | "no_patrol"
  // absent on alerts predating this field, and on collision/ghost_patrol
  cause?: "stillness" | "signal_loss" | "missed_checkpoint" | "short_dwell" | "no_patrol";
}
