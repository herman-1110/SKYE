import {
  collection,
  limit,
  onSnapshot,
  orderBy,
  query,
  where,
  type Unsubscribe,
} from "firebase/firestore";
import { ref, uploadBytesResumable, getDownloadURL, deleteObject } from "firebase/storage";
import { onAuthStateChanged } from "firebase/auth";
import { auth, fsdb, storage } from "@/config/firebase";
import type { FloorRecord } from "@/types/floor";
import type { PatrolLogRecord } from "@/types/patrolLog";

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
    const raw = await res.text().catch(() => res.statusText);
    // FastAPI error bodies are JSON — {"detail": "message"} — not the plain
    // message text. Extract it so callers showing err.message directly (e.g.
    // via toast) get a readable string instead of a raw JSON blob.
    let detail = raw;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // Not JSON — use the raw text as-is.
    }
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
  onTaskReady?: (cancel: () => void) => void,
): Promise<FloorRecord> {
  if (file.size === 0) throw new Error("File is empty");
  if (file.size > MAX_BYTES) throw new Error("File too large — maximum 10MB");
  if (!ALLOWED_TYPES.includes(file.type)) throw new Error("Invalid file type — PNG, JPG, PDF only");

  // Read natural pixel dimensions before upload (images only; PDFs → null).
  // A decode failure means the file is corrupt/truncated — reject it here
  // rather than uploading an image that will never render.
  let image_width_px: number | null = null;
  let image_height_px: number | null = null;
  if (file.type.startsWith("image/")) {
    const dims = await new Promise<{ w: number; h: number } | null>((resolve) => {
      const img = new Image();
      img.onload = () => { resolve({ w: img.naturalWidth, h: img.naturalHeight }); URL.revokeObjectURL(img.src); };
      img.onerror = () => resolve(null);
      img.src = URL.createObjectURL(file);
    });
    if (!dims) throw new Error("Could not read this image — it may be corrupt or empty.");
    image_width_px = dims.w; image_height_px = dims.h;
    console.log("[uploadFloor] image dimensions:", dims.w, "×", dims.h);
  }

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
  onTaskReady?.(() => task.cancel());

  return new Promise((resolve, reject) => {
    task.on(
      "state_changed",
      (snap) => onProgress?.(Math.round((snap.bytesTransferred / snap.totalBytes) * 100)),
      (err) => {
        if (err.code === "storage/canceled") {
          reject(new Error("CANCELLED"));
        } else if (err.code === "storage/unauthorized") {
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
          body: JSON.stringify({ name, floor_number: floorNumber, url, storage_path: storagePath, image_width_px, image_height_px }),
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

export const savePatrolConfig = (
  buildingId: string,
  floorId: string,
  patrolEnabled: boolean,
  patrolRoute: string[],
): Promise<void> =>
  req("PATCH", `/api/buildings/${buildingId}/floors/${floorId}/patrol`, {
    patrol_enabled: patrolEnabled,
    patrol_route: patrolRoute,
  });

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

// ── AP / CCTV ─────────────────────────────────────────────────────────────────

export interface APRecord {
  id: string;
  floor_id: string;
  building_id: string;
  name: string;
  mac: string;
  x_pct: number;
  y_pct: number;
  created_at: string;
  x_m: number;
  y_m: number;
}

export interface CCTVRecord {
  id: string;
  floor_id: string;
  building_id: string;
  name: string;
  x_pct: number;
  y_pct: number;
  created_at: string;
  mac?: string | null;
}

export const listAPs = (buildingId: string, floorId: string): Promise<APRecord[]> =>
  req("GET", `/api/buildings/${buildingId}/floors/${floorId}/aps`);

// x_m/y_m are not part of either request body — the backend derives them
// server-side from x_pct/y_pct + the floor's calibrated scale and ignores
// anything sent here (see floor_routes.py's create_ap/update_ap_position).
export const createAP = (
  buildingId: string,
  floorId: string,
  body: { name: string; mac: string; x_pct: number; y_pct: number },
): Promise<APRecord> =>
  req("POST", `/api/buildings/${buildingId}/floors/${floorId}/aps`, body);

export const updateAPPosition = (
  buildingId: string,
  floorId: string,
  apId: string,
  body: { x_pct: number; y_pct: number },
): Promise<void> =>
  req("PATCH", `/api/buildings/${buildingId}/floors/${floorId}/aps/${apId}/position`, body);

export const deleteAP = (buildingId: string, floorId: string, apId: string): Promise<void> =>
  req("DELETE", `/api/buildings/${buildingId}/floors/${floorId}/aps/${apId}`);

export const listCCTVs = (buildingId: string, floorId: string): Promise<CCTVRecord[]> =>
  req("GET", `/api/buildings/${buildingId}/floors/${floorId}/cctvs`);

export const createCCTV = (
  buildingId: string,
  floorId: string,
  body: { name: string; x_pct: number; y_pct: number; mac?: string | null },
): Promise<CCTVRecord> =>
  req("POST", `/api/buildings/${buildingId}/floors/${floorId}/cctvs`, body);

export const updateCCTVPosition = (
  buildingId: string,
  floorId: string,
  cctvId: string,
  body: { x_pct: number; y_pct: number },
): Promise<void> =>
  req("PATCH", `/api/buildings/${buildingId}/floors/${floorId}/cctvs/${cctvId}/position`, body);

export const deleteCCTV = (buildingId: string, floorId: string, cctvId: string): Promise<void> =>
  req("DELETE", `/api/buildings/${buildingId}/floors/${floorId}/cctvs/${cctvId}`);

export function subscribeToAPs(
  buildingId: string,
  floorId: string,
  callback: (aps: APRecord[]) => void,
): Unsubscribe {
  const q = query(
    collection(fsdb, "buildings", buildingId, "floors", floorId, "access_points"),
    orderBy("created_at"),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => d.data() as APRecord));
  });
}

// Bounded and ordered — unlike patrolLogService.ts's unbounded getDocs() (which
// has zero callers and stays that way). There is no backend endpoint for patrol
// logs and no floor_id/cycle_id field to filter this query on server-side, so
// this pulls the N most recent logs across ALL floors/guards and the caller
// filters to its own floor client-side via checkpoint_id -> AP mac membership.
export function subscribeToPatrolLogs(
  limitN: number,
  callback: (logs: PatrolLogRecord[]) => void,
): Unsubscribe {
  const q = query(
    collection(fsdb, "patrol_logs"),
    orderBy("expected_arrival", "desc"),
    limit(limitN),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => d.data() as PatrolLogRecord));
  });
}

// One guard's full log history, newest first. Requires a composite index on
// patrol_logs (guard_id ASC, expected_arrival DESC) — see firestore.indexes.json
// — because Firestore needs one for an equality filter combined with an
// orderBy on a different field (verified directly against this project's
// Firestore: without it, this query throws FailedPrecondition). Deploy via
// `firebase deploy --only firestore:indexes` before this is used in production.
export function subscribeToPatrolLogsByGuard(
  guardId: string,
  limitN: number,
  callback: (logs: PatrolLogRecord[]) => void,
): Unsubscribe {
  const q = query(
    collection(fsdb, "patrol_logs"),
    where("guard_id", "==", guardId),
    orderBy("expected_arrival", "desc"),
    limit(limitN),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => d.data() as PatrolLogRecord));
  });
}

export function subscribeToCCTVs(
  buildingId: string,
  floorId: string,
  callback: (cctvs: CCTVRecord[]) => void,
): Unsubscribe {
  const q = query(
    collection(fsdb, "buildings", buildingId, "floors", floorId, "cctvs"),
    orderBy("created_at"),
  );
  return onSnapshot(q, (snap) => {
    callback(snap.docs.map((d) => d.data() as CCTVRecord));
  });
}
