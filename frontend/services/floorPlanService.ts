import { collection, onSnapshot, query, where, type Unsubscribe } from "firebase/firestore";
import { ref, uploadBytesResumable, getDownloadURL, deleteObject } from "firebase/storage";
import { onAuthStateChanged } from "firebase/auth";
import { auth, fsdb, storage } from "@/config/firebase";
import type { FloorPlanRecord } from "@/types/floorPlan";

type Callback<T> = (data: T) => void;

export function subscribeToFloorPlans(userId: string, callback: Callback<FloorPlanRecord[]>): Unsubscribe {
  const q = query(collection(fsdb, "floor_plans"), where("user_id", "==", userId));
  return onSnapshot(q, (snap) => {
    const plans = snap.docs
      .map((d) => d.data() as FloorPlanRecord)
      .sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at));
    callback(plans);
  });
}

export function subscribeToActiveFloorPlan(callback: Callback<FloorPlanRecord | null>): Unsubscribe {
  const q = query(collection(fsdb, "floor_plans"), where("is_active", "==", true));
  return onSnapshot(q, (snap) => {
    callback(snap.empty ? null : (snap.docs[0].data() as FloorPlanRecord));
  });
}

const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/webp", "application/pdf"];
const MAX_BYTES = 10 * 1024 * 1024;

export async function uploadFloorPlan(
  file: File,
  name: string,
  userId: string,
  _token?: string,
  onProgress?: (pct: number) => void,
): Promise<FloorPlanRecord> {
  if (file.size > MAX_BYTES) throw new Error("File too large — maximum 10MB");
  if (!ALLOWED_TYPES.includes(file.type)) throw new Error("Invalid file type — PNG, JPG, PDF only");

  if (!auth.currentUser) {
    await new Promise<void>((resolve) => {
      const unsub = onAuthStateChanged(auth, (u) => {
        if (u) { unsub(); resolve(); }
      });
    });
  }

  const currentUser = auth.currentUser;
  if (!currentUser) throw new Error("User not authenticated");

  const token = await currentUser.getIdToken();

  const storagePath = `floor_plans/${userId}/${Date.now()}_${file.name}`;
  const storageRef = ref(storage, storagePath);
  const task = uploadBytesResumable(storageRef, file);

  return new Promise((resolve, reject) => {
    task.on(
      "state_changed",
      (snap) => onProgress?.(Math.round((snap.bytesTransferred / snap.totalBytes) * 100)),
      (err) => {
        if (err.code === "storage/unauthorized") {
          reject(new Error("Storage permission denied — check Firebase Storage rules"));
        } else {
          reject(new Error("Upload failed. Please try again."));
        }
      },
      async () => {
        const url = await getDownloadURL(task.snapshot.ref);
        const freshToken = await auth.currentUser?.getIdToken() ?? token;
        const res = await fetch("/api/floor-plans", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${freshToken}` },
          body: JSON.stringify({ user_id: userId, name, url, storage_path: storagePath }),
        });
        if (!res.ok) { reject(new Error(`Floor plan creation failed: ${res.status}`)); return; }
        resolve(await res.json());
      },
    );
  });
}

export async function updateScale(floorPlanId: string, scalePixelsPerMeter: number): Promise<void> {
  const token = await auth.currentUser?.getIdToken();
  const res = await fetch(`/api/floor-plans/${floorPlanId}/scale`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ scale_pixels_per_meter: scalePixelsPerMeter }),
  });
  if (!res.ok) throw new Error(`Scale update failed: ${res.status}`);
}

function resolveStoragePath(storagePathOrUrl: string): string {
  if (!storagePathOrUrl.startsWith("https://")) return storagePathOrUrl;
  // Parse path from Firebase Storage download URL:
  // https://firebasestorage.googleapis.com/v0/b/<bucket>/o/<encoded-path>?alt=media&token=...
  const afterO = storagePathOrUrl.indexOf("/o/") + 3;
  const beforeQuery = storagePathOrUrl.indexOf("?");
  return decodeURIComponent(storagePathOrUrl.substring(afterO, beforeQuery === -1 ? undefined : beforeQuery));
}

export async function deleteFloorPlan(floorPlanId: string, storagePathOrUrl: string): Promise<void> {
  // Step 1: Delete file from Firebase Storage — if this fails, Firestore is untouched
  const storagePath = resolveStoragePath(storagePathOrUrl);
  await deleteObject(ref(storage, storagePath));

  // Step 2: Delete Firestore document via backend — only reached if Storage delete succeeded
  const token = await auth.currentUser?.getIdToken();
  const res = await fetch(`/api/floor-plans/${floorPlanId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Firestore delete failed: ${res.status}`);
}

export async function activateFloorPlan(floorPlanId: string, userId: string): Promise<void> {
  const token = await auth.currentUser?.getIdToken();
  const res = await fetch(`/api/floor-plans/${floorPlanId}/activate`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) throw new Error(`Activation failed: ${res.status}`);
}
