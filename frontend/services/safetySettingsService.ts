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
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export interface SafetySettings {
  man_down_minutes: number;
  collision_distance_m: number;
  updated_at?: string;
}

export interface SafetySettingsUpdate {
  man_down_minutes: number;
  collision_distance_m: number;
}

export const getSafetySettings = (): Promise<SafetySettings> =>
  req<SafetySettings>("GET", "/api/settings/safety");

export const updateSafetySettings = (body: SafetySettingsUpdate): Promise<SafetySettings> =>
  req<SafetySettings>("PUT", "/api/settings/safety", body);
