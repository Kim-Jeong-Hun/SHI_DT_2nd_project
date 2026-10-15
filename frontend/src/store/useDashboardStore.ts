import { create } from "zustand";
import type { VesselSelectionId } from "../data/mockMarket";

interface DashboardState {
  vesselId: VesselSelectionId;
  darkMode: boolean;
  setVesselId: (id: VesselSelectionId) => void;
  setDarkMode: (darkMode: boolean) => void;
}

/** UI preferences only; market datasets are intentionally NOT kept in Zustand. */
export const useDashboardStore = create<DashboardState>((set) => ({
  vesselId: "all",
  darkMode: false,
  setVesselId: (vesselId) => set({ vesselId }),
  setDarkMode: (darkMode) => set({ darkMode }),
}));
