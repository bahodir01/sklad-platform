import { create } from "zustand";

/**
 * Статус сессии (§6, §7.4). ЕДИНСТВЕННОЕ, что лежит в Zustand по auth: его
 * обязан писать client.ts/refresh из обработчика 401 — императивно, вне дерева
 * React. Токен сюда НЕ кладётся (persist на токене = запрещённый localStorage).
 */
export type SessionStatus = "unknown" | "authenticated" | "anonymous";

interface SessionState {
  status: SessionStatus;
  setStatus: (status: SessionStatus) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  status: "unknown",
  setStatus: (status) => set({ status }),
}));

/** Императивный доступ вне React (для refresh/логаут-хендлеров). */
export const sessionStore = {
  setStatus: (status: SessionStatus) => useSessionStore.getState().setStatus(status),
  getStatus: () => useSessionStore.getState().status,
};
