export interface FloorRecord {
  id: string;
  building_id: string;
  name: string;
  floor_number: number;
  url: string;
  storage_path: string;
  scale_pixels_per_meter: number | null;
  is_active: boolean;
  uploaded_at: string;
  image_width_px?: number | null;
  image_height_px?: number | null;
  patrol_enabled?: boolean;
  patrol_route?: string[];
  // Global backend setting (PATROL_PROXIMITY_RADIUS_M), not per-floor data —
  // crosses on every floor response so the frontend has one source of truth
  // instead of a hardcoded copy (Prompt 117).
  patrol_proximity_radius_m?: number;
}
