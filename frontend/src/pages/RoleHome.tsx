import { Navigate } from "react-router-dom";
import { useMe } from "@/entities/session/api/use-me";
import { ROUTES } from "@/shared/config/routes";

/**
 * Точка входа с «/» (§5, Ф-4). Роль решает, куда попасть после логина:
 *   admin            → очередь «К печати» (его основная операционная задача);
 *   teacher | worker → «Мои заявки» (у сотрудника нет админских экранов).
 * До разрешения /auth/me — тихий лоадер, чтобы не мигнуть чужим маршрутом.
 */
export function RoleHome() {
  const { data: me, isLoading } = useMe();

  if (isLoading || !me) {
    return (
      <div className="p-6 text-sm text-muted-foreground" role="status" aria-live="polite">
        Загрузка…
      </div>
    );
  }

  return (
    <Navigate to={me.role === "admin" ? ROUTES.toPrint : ROUTES.myRequests} replace />
  );
}
