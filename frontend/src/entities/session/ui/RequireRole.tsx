import { Navigate, Outlet } from "react-router-dom";
import type { UserRole } from "@/shared/api/schema";
import { ROUTES } from "@/shared/config/routes";
import { useMe } from "../api/use-me";

/**
 * Гвард роли (§5). На этапе 1 НИ ОДНИМ маршрутом не используется — пишется
 * заранее: с этапа 3 под него уходят /to-print, /reports/*, /cash. Отдаёт /403
 * (не /login): «не твоя роль» ≠ «войди заново».
 */
export function RequireRole({ roles }: { roles: UserRole[] }) {
  const { data: me, isLoading } = useMe();

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-muted-foreground" role="status" aria-live="polite">
        Загрузка…
      </div>
    );
  }
  if (!me || !roles.includes(me.role)) {
    return <Navigate to={ROUTES.forbidden} replace />;
  }
  return <Outlet />;
}
