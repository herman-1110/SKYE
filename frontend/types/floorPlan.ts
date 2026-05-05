export interface FloorPlanRecord {
  floor_plan_id: string;
  user_id: string;
  name: string;
  url: string;                          // Firebase Storage download URL
  uploaded_at: string;                  // ISO 8601
  is_active: boolean;
  scale_pixels_per_meter: number | null; // null until calibrated
}
