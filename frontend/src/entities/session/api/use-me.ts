import { useQuery } from "@tanstack/react-query";
import { authKeys } from "@/shared/api/query-keys";
import { useSessionStore } from "../model/session-store";
import { fetchMe } from "./auth-api";

/**
 * Текущий пользователь ['auth','me'] (§10). Запрос идёт только когда сессия
 * authenticated — до разрешения AuthBootstrap токена ещё нет.
 */
export function useMe() {
  const status = useSessionStore((s) => s.status);
  return useQuery({
    queryKey: authKeys.me,
    queryFn: ({ signal }) => fetchMe(signal),
    enabled: status === "authenticated",
    staleTime: 5 * 60 * 1000,
  });
}
