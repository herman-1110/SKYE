import { auth } from "@/config/firebase";

async function token(): Promise<string> {
  const t = await auth.currentUser?.getIdToken();
  if (!t) throw new Error("Not authenticated");
  return t;
}

async function req<T>(method: string, path: string): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { Authorization: `Bearer ${await token()}` },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(detail);
  }
  return res.json();
}

export type SimMode = "patrol" | "events" | "shift";

export interface SimStatus {
  running: boolean;
  mode: SimMode | null;
}

export const simulationService = {
  start: (mode: SimMode) =>
    req<{ status: string; mode: SimMode }>("POST", `/api/simulation/start?mode=${mode}`),

  stop: () =>
    req<{ status: string; mode: SimMode | null }>("POST", "/api/simulation/stop"),

  status: () =>
    req<SimStatus>("GET", "/api/simulation/status"),
};
