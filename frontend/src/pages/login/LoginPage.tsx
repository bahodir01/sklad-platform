import { Navigate } from "react-router-dom";
import { useSessionStore } from "@/entities/session/model/session-store";
import { LoginForm } from "@/features/auth/login-form/LoginForm";
import { Card, CardContent } from "@/shared/ui/card";
import { HOME_ROUTE } from "@/shared/config/routes";

/**
 * Экран входа (§6). Аутентифицированного редиректит на точку входа —
 * логин не показываем повторно.
 */
export function LoginPage() {
  const status = useSessionStore((s) => s.status);
  if (status === "authenticated") {
    return <Navigate to={HOME_ROUTE} replace />;
  }
  return (
    <Card>
      <CardContent className="pt-6">
        <LoginForm />
      </CardContent>
    </Card>
  );
}
