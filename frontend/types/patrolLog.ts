export interface PatrolLogRecord {
  log_id: string;
  guard_id: string;
  checkpoint_id: string;
  checkpoint_name: string;
  expected_arrival: string;       // ISO 8601
  actual_arrival: string | null;  // ISO 8601; null if guard missed checkpoint
  dwell_time_seconds: number;
  min_dwell_required: number;
  ble_detected: boolean;
  vigi_detected: boolean;
  compliant: boolean;
  shift_id: string;
  cycle_id?: string;  // absent on logs predating the real-time tracker (Prompt 110)
  // True only for a checkpoint the time-boxed window closed before reaching
  // (Prompt 122) — never a violation. Absent (falsy) on every log written
  // before Prompt 122, which is exactly right: those render under the old
  // wrap-model semantics unchanged, since the field didn't exist yet.
  not_in_window?: boolean;
}
