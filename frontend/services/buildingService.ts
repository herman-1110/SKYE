import { collection, onSnapshot, query, where, type Unsubscribe } from "firebase/firestore";
import { auth, fsdb } from "@/config/firebase";
import type { BuildingRecord } from "@/types/building";

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

export function subscribeToBuildings(
  userId: string,
  callback: (buildings: BuildingRecord[]) => void,
): Unsubscribe {
  const q = query(collection(fsdb, "buildings"), where("user_id", "==", userId));
  return onSnapshot(q, (snap) => {
    const buildings = snap.docs
      .map((d) => d.data() as BuildingRecord)
      .sort((a, b) => b.created_at.localeCompare(a.created_at));
    callback(buildings);
  });
}

export const createBuilding = (name: string, description: string): Promise<BuildingRecord> =>
  req("POST", "/api/buildings", { name, description });

export const renameBuilding = (buildingId: string, name: string): Promise<void> =>
  req("PATCH", `/api/buildings/${buildingId}`, { name });

export const deleteBuilding = (buildingId: string): Promise<void> =>
  req("DELETE", `/api/buildings/${buildingId}`);
