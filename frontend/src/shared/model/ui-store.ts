import { create } from "zustand";

/**
 * UI-стор (§7.4). sidebarCollapsed переживает навигацию между страницами —
 * поэтому Zustand, а не useState страницы. Никаких копий серверных данных здесь.
 */
interface UiState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: false,
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
}));
