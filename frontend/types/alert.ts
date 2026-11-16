export type AlertType =
  | "man_down"
  | "possible_man_down"     // stillness seen by only one or two APs (amber)
  | "positioning_offline"   // no AP reports reaching SKYE; person_id and zone are ""
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
  // possible_man_down: "stillness"
  // patrol_violation: "missed_checkpoint" | "short_dwell" | "no_patrol"
  // absent on alerts predating this field, and on collision/ghost_patrol/positioning_offline
  cause?: "stillness" | "signal_loss" | "missed_checkpoint" | "short_dwell" | "no_patrol";
  // Stillness man_down and possible_man_down from Prompt 145 on: the floor
  // and the episode's anchor (metres) when the alert was raised
  floor_id?: string;
  anchor_x?: number;
  anchor_y?: number;
  // Set once, when an admin closes the pop-up for everyone (Prompt 145).
  // Acknowledged isn't resolved: the alert stays active until feedback.
  acknowledged_at?: string;     // ISO 8601, UTC
  acknowledged_by?: string;     // the admin's display name, or "admin"
  acknowledged_by_uid?: string;
}
