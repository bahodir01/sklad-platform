import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { refreshAccessToken, registerAuthLostHandler } from "@/shared/api/refresh";
import { useSessionStore } from "@/entities/session/model/session-store";

/**
 * Тихий refresh при старте (§6). Access-токен живёт в памяти и умирает на F5;
 * refresh-cookie живёт 30 дней. Без этого гейта гварды успеют отработать на
 * пустом токене и выкинут живую сессию на /login.
 *
 * 200 → status='authenticated' (client дальше сам подтянет /auth/me);
 * 401 → status='anonymous' (нормальный путь для незалогиненного, НЕ ошибка —
 *        тост не показываем).
 * Пока не разрешилось — полноэкранный лоадер, роутер не рендерится.
 */
export function AuthBootstrap({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const setStatus = useSessionStore((s) => s.setStatus);
  const status = useSessionStore((s) => s.status);
  const [booted, setBooted] = useState(false);
  const started = useRef(false);

  // Обработчик «сессия потеряна» (окончательный провал 401): гасим сессию и
  // чистим кэш. Редирект делает RequireAuth, реагируя на status='anonymous'.
  useEffect(() => {
    registerAuthLostHandler(() => {
      setStatus("anonymous");
      queryClient.clear();
    });
  }, [queryClient, setStatus]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void (async () => {
      const ok = await refreshAccessToken();
      setStatus(ok ? "authenticated" : "anonymous");
      setBooted(true);
    })();
  }, [setStatus]);

  if (!booted && status === "unknown") {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-background"
        role="status"
        aria-live="polite"
      >
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
          <p className="text-sm">Загрузка…</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
