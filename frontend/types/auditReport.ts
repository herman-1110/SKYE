export interface AuditReportRecord {
  report_id: string;
  shift_id: string;
  guard_id: string;
  generated_at: string;     // ISO 8601
  patrol_summary: string;
  alert_summary: string;
  rag_examples_used: string[];
  report_text: string;
  model_used: string;
}
