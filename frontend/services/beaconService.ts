import { auth } from "@/config/firebase";
import { onAuthStateChanged } from "firebase/auth"

async function token(): Promise<string> {
  if (!auth.currentUser) {
    await new Promise<void>((resolve) => {
      const unsub = onAuthStateChanged(auth, (u) => {
        if (u) { unsub(); resolve(); }
      });
    });
  }
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

export type PersonType = "guard" | "worker" | "forklift";

export interface BeaconRecord {
  id: string;
  uuid: string;
  major: string;
  minor: string;
  person_id: string;
  person_type: PersonType;
  label: string;
  building_id?: string | null;
  tx_power: number;
  created_at: string;
  updated_at: string;
}

export interface BeaconCreate {
  uuid: string;
  major: string;
  minor: string;
  person_id: string;
  person_type: PersonType;
  label: string;
  building_id?: string | null;
  tx_power?: number;
}

export interface BeaconUpdate {
  person_id?: string;
  person_type?: PersonType;
  label?: string;
  building_id?: string | null;
  tx_power?: number;
}

export const listBeacons = (): Promise<BeaconRecord[]> =>
  req("GET", "/api/beacons");

export const createBeacon = (body: BeaconCreate): Promise<BeaconRecord> =>
  req("POST", "/api/beacons", body);

export const updateBeacon = (id: string, patch: BeaconUpdate): Promise<BeaconRecord> =>
  req("PATCH", `/api/beacons/${id}`, patch);

export const deleteBeacon = (id: string): Promise<void> =>
  req("DELETE", `/api/beacons/${id}`);
