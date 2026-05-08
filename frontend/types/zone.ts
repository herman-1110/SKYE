export interface ZoneRecord {
  id: string;
  floor_plan_id: string;
  name: string;
  color: string;          // hex with alpha e.g. "#ef444433"
  is_high_risk: boolean;
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
  created_at: string;
  created_by: string;
}
