import { collection, onSnapshot, query, where, orderBy, type Unsubscribe } from "firebase/firestore";
import { ref, uploadBytes, getDownloadURL } from "firebase/storage";
import { fsdb, storage } from "@/config/firebase";
import type { FloorPlanRecord } from "@/types/floorPlan";

type Callback<T> = (data: T) => void;

export function subscribeToFloorPlans(userId: string, callback: Callback<FloorPlanRecord[]>): Unsubscribe {
  const q = query(
    collection(fsdb, "floor_plans"),
    where("user_id", "==", userId),
    orderBy("uploaded_at", "desc"),
  );
  return onSnapshot(q, (snap) =>
    callback(snap.docs.map((d) => d.data() as FloorPlanRecord)),
  );
}

export function subscribeToActiveFloorPlan(callback: Callback<FloorPlanRecord | null>): Unsubscribe {
  const q = query(collection(fsdb, "floor_plans"), where("is_active", "==", true));
  return onSnapshot(q, (snap) => {
    callback(snap.empty ? null : (snap.docs[0].data() as FloorPlanRecord));
  });
}

export async function uploadFloorPlan(
  file: File,
  name: string,
  userId: string,
): Promise<FloorPlanRecord> {
  // 1. Upload image to Firebase Storage
  const storageRef = ref(storage, `floor_plans/${userId}/${Date.now()}_${file.name}`);
  await uploadBytes(storageRef, file);
  const url = await getDownloadURL(storageRef);

  // 2. Save metadata to backend (which writes to Firestore)
  const res = await fetch("/api/floor-plans", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, name, url }),
  });
  if (!res.ok) throw new Error(`Floor plan creation failed: ${res.status}`);
  return res.json();
}

export async function updateScale(floorPlanId: string, scalePixelsPerMeter: number): Promise<void> {
  const res = await fetch(`/api/floor-plans/${floorPlanId}/scale`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scale_pixels_per_meter: scalePixelsPerMeter }),
  });
  if (!res.ok) throw new Error(`Scale update failed: ${res.status}`);
}

export async function activateFloorPlan(floorPlanId: string, userId: string): Promise<void> {
  const res = await fetch(`/api/floor-plans/${floorPlanId}/activate`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) throw new Error(`Activation failed: ${res.status}`);
}
