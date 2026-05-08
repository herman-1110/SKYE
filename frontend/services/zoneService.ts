import { auth } from "@/config/firebase";
import type { ZoneRecord } from "@/types/zone";

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

const base = (b: string, f: string) => `/api/buildings/${b}/floors/${f}/zones`;

export const getZones = (buildingId: string, floorId: string): Promise<ZoneRecord[]> =>
  req("GET", base(buildingId, floorId));

export const createZone = (
  buildingId: string,
  floorId: string,
  zone: Omit<ZoneRecord, "id" | "floor_plan_id" | "created_at" | "created_by">,
): Promise<ZoneRecord> =>
  req("POST", base(buildingId, floorId), zone);

export const updateZone = (
  buildingId: string,
  floorId: string,
  zoneId: string,
  fields: Partial<ZoneRecord>,
): Promise<ZoneRecord> =>
  req("PATCH", `${base(buildingId, floorId)}/${zoneId}`, fields);

export const deleteZone = (buildingId: string, floorId: string, zoneId: string): Promise<void> =>
  req("DELETE", `${base(buildingId, floorId)}/${zoneId}`);

export async function aiDetectZones(
  buildingId: string,
  floorId: string,
): Promise<Omit<ZoneRecord, "id" | "floor_plan_id" | "created_at" | "created_by">[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90_000);
  try {
    const t = await token();
    const res = await fetch(`${base(buildingId, floorId)}/ai-detect`, {
      method: "POST",
      headers: { Authorization: `Bearer ${t}` },
      signal: controller.signal,
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => res.statusText);
      throw new Error(detail);
    }
    return res.json();
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("AI zone detection timed out after 90 seconds.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
