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
}
