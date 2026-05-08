import {
  collection,
  onSnapshot,
  orderBy,
  query,
  type Unsubscribe,
} from "firebase/firestore";
import { ref, uploadBytesResumable, getDownloadURL, deleteObject } from "firebase/storage";
import { onAuthStateChanged } from "firebase/auth";
import { auth, fsdb, storage } from "@/config/firebase";
import type { FloorRecord } from "@/types/floor";

async function token(): Promise<string> {
  const t = await auth.currentUser?.getIdToken();
  if (!t) throw new Error("Not authenticated");
  return t;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: {
      Authorization: `Bearer ${await token()}`,
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail);
  }
  return res.json();
}

export function subscribeToFloors(
  buildingId: string,
  callback: (floors: FloorRecord[]) => void,
): Unsubscribe {
  const q = query(
    collection(fsdb, "buildings", buildingId, "floors"),
    orderBy("floor_number"),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => d.data() as FloorRecord));
  });
}

const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/webp", "application/pdf"];
const MAX_BYTES = 10 * 1024 * 1024;

export async function uploadFloor(
  file: File,
  buildingId: string,
  name: string,
  floorNumber: number,
  onProgress?: (pct: number) => void,
): Promise<FloorRecord> {
  if (file.size > MAX_BYTES) throw new Error("File too large — maximum 10MB");
  if (!ALLOWED_TYPES.includes(file.type)) throw new Error("Invalid file type — PNG, JPG, PDF only");

  if (!auth.currentUser) {
    await new Promise<void>((resolve) => {
      const unsub = onAuthStateChanged(auth, (u) => {
        if (u) { unsub(); resolve(); }
      });
    });
  }
  if (!auth.currentUser) throw new Error("User not authenticated");

  const storagePath = `buildings/${buildingId}/floors/${Date.now()}_${file.name}`;
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
        const freshToken = await auth.currentUser?.getIdToken() ?? await token();
        const res = await fetch(`/api/buildings/${buildingId}/floors`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${freshToken}` },
          body: JSON.stringify({ name, floor_number: floorNumber, url, storage_path: storagePath }),
        });
        if (!res.ok) { reject(new Error(`Floor creation failed: ${res.status}`)); return; }
        resolve(await res.json());
      },
    );
  });
}

export const updateFloorScale = (
  buildingId: string,
  floorId: string,
  scale: number,
): Promise<void> =>
  req("PATCH", `/api/buildings/${buildingId}/floors/${floorId}/scale`, {
    scale_pixels_per_meter: scale,
  });

export const activateFloor = (buildingId: string, floorId: string): Promise<void> =>
  req("PATCH", `/api/buildings/${buildingId}/floors/${floorId}/activate`);

export const deactivateFloor = (buildingId: string, floorId: string): Promise<void> =>
  req("PATCH", `/api/buildings/${buildingId}/floors/${floorId}/deactivate`);

export const renameFloor = (buildingId: string, floorId: string, name: string): Promise<void> =>
  req("PATCH", `/api/buildings/${buildingId}/floors/${floorId}`, { name });

export async function deleteFloor(
  buildingId: string,
  floorId: string,
  storagePath: string,
): Promise<void> {
  await deleteObject(ref(storage, storagePath));
  await req("DELETE", `/api/buildings/${buildingId}/floors/${floorId}`);
}
