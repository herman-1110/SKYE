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
}
