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
  is_stationary: boolean;
}
