import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useSessionStore } from "../model/session-store";
import { ROUTES } from "@/shared/config/routes";

/**
 * Гвард аутентификации (§5). Статус сессии разрешён к моменту рендера роутера —
 * AuthBootstrap держит лоадер до этого. 'anonymous' → на /login с запоминанием
 * from; 'authenticated' → отдаём вложенные маршруты.
 */
export function RequireAuth() {
  const status = useSessionStore((s) => s.status);
  const location = useLocation();

  if (status !== "authenticated") {
    return <Navigate to={ROUTES.login} replace state={{ from: location }} />;
  }
  return <Outlet />;
}
