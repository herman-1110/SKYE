import type { PositionRecord } from "@/types/position";
import type { AlertRecord } from "@/types/alert";

async function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}` };
}

export async function getMyPosition(token: string): Promise<PositionRecord | null> {
  const res = await fetch("/api/guard/position", { headers: await authHeaders(token) });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to fetch position");
  return res.json();
}

export async function getMyPatrol(token: string): Promise<object[]> {
  const res = await fetch("/api/guard/patrol", { headers: await authHeaders(token) });
  if (!res.ok) throw new Error("Failed to fetch patrol logs");
  return res.json();
}

export async function getMyAlerts(token: string): Promise<AlertRecord[]> {
  const res = await fetch("/api/guard/alerts", { headers: await authHeaders(token) });
  if (!res.ok) throw new Error("Failed to fetch alerts");
  return res.json();
}
