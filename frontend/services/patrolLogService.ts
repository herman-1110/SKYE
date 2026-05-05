import { collection, getDocs } from "firebase/firestore";
import { fsdb } from "@/config/firebase";

export interface ShiftOption {
  shift_id: string;
  guard_id: string;
  date: string;
}

export async function getDistinctShifts(): Promise<ShiftOption[]> {
  const snap = await getDocs(collection(fsdb, "patrol_logs"));
  const seen = new Map<string, ShiftOption>();
  snap.docs.forEach((doc) => {
    const d = doc.data();
    if (d.shift_id && !seen.has(d.shift_id)) {
      seen.set(d.shift_id, {
        shift_id: d.shift_id,
        guard_id: d.guard_id ?? "—",
        date: d.expected_arrival?.slice(0, 10) ?? "—",
      });
    }
  });
  return Array.from(seen.values()).reverse();
}
