import { create } from "zustand";
import type { AlertRecord } from "@/types/alert";
import type { AuditReportRecord } from "@/types/auditReport";
import type { BuildingRecord } from "@/types/building";
import type { PositionRecord } from "@/types/position";
import type { UserRecord } from "@/types/user";

interface DashboardState {
  // live subscriptions (populated by DataSubscriptions in layout)
  positions: Record<string, PositionRecord>;
  alerts: Record<string, AlertRecord>;
  selectedWorkerId: string | null;
  activeShiftId: string | null;
  setPositions: (positions: Record<string, PositionRecord>) => void;
  setAlerts: (alerts: Record<string, AlertRecord>) => void;
  setSelectedWorker: (id: string | null) => void;
  setActiveShift: (id: string | null) => void;

  // cached tab data — survives tab switches
  cachedReports: AuditReportRecord[];
  cachedUsers: UserRecord[];
  cachedBuildings: BuildingRecord[];
  setCachedReports: (reports: AuditReportRecord[]) => void;
  setCachedUsers: (users: UserRecord[]) => void;
  setCachedBuildings: (buildings: BuildingRecord[]) => void;

  // user UI preferences — survive remount when navigating between dashboard tabs
  showZones: boolean;
  toggleShowZones: () => void;
  showPatrolRoute: boolean;
  toggleShowPatrolRoute: () => void;
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

  cachedReports: [],
  cachedUsers: [],
  cachedBuildings: [],
  setCachedReports: (cachedReports) => set({ cachedReports }),
  setCachedUsers: (cachedUsers) => set({ cachedUsers }),
  setCachedBuildings: (cachedBuildings) => set({ cachedBuildings }),

  showZones: true,
  toggleShowZones: () => set((s) => ({ showZones: !s.showZones })),
  showPatrolRoute: true,
  toggleShowPatrolRoute: () => set((s) => ({ showPatrolRoute: !s.showPatrolRoute })),
}));
