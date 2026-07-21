import { Badge } from "@/shared/ui/badge";
import { roleLabel } from "@/shared/config/roles";
import type { UserRole } from "@/shared/api/model-types";

/**
 * Роль пользователя бейджем (§11: цвет не единственный сигнал — текст
 * (roleLabel) читается и в ч/б). admin выделен акцентом (административные
 * права), teacher/worker — мягкие семантические цвета.
 */
export function RoleBadge({ role }: { role: UserRole }) {
  const variant = role === "admin" ? "default" : role === "teacher" ? "info" : "secondary";
  return <Badge variant={variant}>{roleLabel(role)}</Badge>;
}
