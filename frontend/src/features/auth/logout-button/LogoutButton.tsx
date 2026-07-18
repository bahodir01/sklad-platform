import { useState } from "react";
import { LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { logout } from "@/entities/session/api/auth-api";
import { tokenStore } from "@/entities/session/model/token-store";
import { useSessionStore } from "@/entities/session/model/session-store";
import { ROUTES } from "@/shared/config/routes";
import { Button } from "@/shared/ui/button";

/**
 * Выход (§6): POST /auth/logout → tokenStore.clear() → queryClient.clear() →
 * /login. Чистка кэша обязательна: без неё следующий пользователь на том же
 * браузере увидит справочники и ФИО предыдущего из кэша Query.
 */
export function LogoutButton() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setStatus = useSessionStore((s) => s.setStatus);
  const [pending, setPending] = useState(false);

  const handleLogout = async () => {
    setPending(true);
    try {
      await logout();
    } catch {
      // Даже если серверный logout не удался — локально гасим сессию.
    } finally {
      tokenStore.clear();
      setStatus("anonymous");
      queryClient.clear();
      navigate(ROUTES.login, { replace: true });
    }
  };

  return (
    <Button variant="ghost" size="sm" onClick={handleLogout} disabled={pending}>
      <LogOut />
      Выйти
    </Button>
  );
}
