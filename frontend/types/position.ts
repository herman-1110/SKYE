export interface PositionRecord {
  beacon_mac: string;
  person_id: string;
  person_type: "guard" | "worker" | "forklift";
  x: number;
  y: number;
  zone: string;
  timestamp: string;         // ISO 8601
  predicted_x: number | null;
  predicted_y: number | null;
  pixel_x: number | null;   // metres × scale_pixels_per_meter; null until floor plan is calibrated
  pixel_y: number | null;
  is_stationary: boolean;
  floor_id: string;
  building_id: string;
  label: string;
  radius_m: number | null;
  is_approximate: boolean;
}
