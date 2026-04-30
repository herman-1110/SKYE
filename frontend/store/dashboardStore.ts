import { create } from "zustand";
import type { AlertRecord } from "@/types/alert";
import type { PositionRecord } from "@/types/position";

interface DashboardState {
  positions: Record<string, PositionRecord>;
  alerts: Record<string, AlertRecord>;
  selectedWorkerId: string | null;
  activeShiftId: string | null;
  setPositions: (positions: Record<string, PositionRecord>) => void;
  setAlerts: (alerts: Record<string, AlertRecord>) => void;
  setSelectedWorker: (id: string | null) => void;
  setActiveShift: (id: string | null) => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  positions: {},
  alerts: {},
  selectedWorkerId: null,
  activeShiftId: null,
  setPositions: (positions) => set({ positions }),
  setAlerts: (alerts) => set({ alerts }),
  setSelectedWorker: (selectedWorkerId) => set({ selectedWorkerId }),
  setActiveShift: (activeShiftId) => set({ activeShiftId }),
}));
