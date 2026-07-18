import { useMe } from "../api/use-me";
import { can } from "./can";
import type { Permission } from "@/shared/config/roles";

/**
 * Удобный хук над can() — избавляет страницы от повторного useMe()+can().
 * useCan('catalog:write') === (role === 'admin'). UX-слой, не защита (§5).
 */
export function useCan(permission: Permission): boolean {
  const { data: me } = useMe();
  return can(me, permission);
}
