import type { components } from "@/shared/api/schema";
import type { Permission } from "@/shared/config/roles";

type User = components["schemas"]["UserRead"];

/**
 * can() — единственный источник «можно писать» (§5). Разделение чтение/запись
 * внутри экрана делает ОНА, а не роутер: не-админ видит те же таблицы без
 * кнопок «Добавить»/«Изменить»/«В архив». Это UX-слой; запись закрывает
 * require_admin на бэкенде.
 */
export function can(user: User | null | undefined, permission: Permission): boolean {
  if (!user) return false;
  switch (permission) {
    case "catalog:write":
      return user.role === "admin";
    default:
      return false;
  }
}
