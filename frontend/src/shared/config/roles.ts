import type { UserRole } from "../api/schema";

/** Роли RBAC (ТЗ §1, backend shared/enums.py:UserRole). */
export const ROLES: Record<UserRole, string> = {
  admin: "Администратор",
  teacher: "Учитель",
  worker: "Работник",
};

export function roleLabel(role: UserRole): string {
  return ROLES[role] ?? role;
}

/** Права уровня приложения. can() — единственный источник «можно писать». */
export type Permission = "catalog:write";
