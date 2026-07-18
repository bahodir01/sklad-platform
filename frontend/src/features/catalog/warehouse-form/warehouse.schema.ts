import { z } from "zod";
import type { components } from "@/shared/api/schema";

type WarehouseCreate = components["schemas"]["WarehouseCreate"];
type WarehouseUpdate = components["schemas"]["WarehouseUpdate"];

/**
 * Единый набор значений формы склада; create и update различаются составом
 * ОТПРАВЛЯЕМОГО (см. билдеры ниже), а не разметкой. Границы — из контракта
 * (§8.3): code 1..32, name 1..255, address max 500, allows_issuance boolean.
 */
export const warehouseFormSchema = z.object({
  code: z.string().min(1).max(32),
  name: z.string().min(1).max(255),
  address: z.string().max(500),
  allows_issuance: z.boolean(),
  status: z.enum(["active", "archived"]),
});

export type WarehouseFormValues = z.infer<typeof warehouseFormSchema>;

const normAddress = (v: string | undefined): string | null => {
  const t = (v ?? "").trim();
  return t.length > 0 ? t : null;
};

/**
 * Тело создания — ровно create-поля (§8.3): code, name, address, allows_issuance.
 * status в create НЕ входит (api.create=false) — тип WarehouseCreate это
 * гарантирует на компиляции: лишний ключ здесь не скомпилируется.
 */
export function toWarehouseCreate(v: WarehouseFormValues): WarehouseCreate {
  return {
    code: v.code,
    name: v.name,
    address: normAddress(v.address),
    allows_issuance: v.allows_issuance,
  };
}

/** Тело правки — update-поля: code, name, address, allows_issuance, status. */
export function toWarehouseUpdate(v: WarehouseFormValues): WarehouseUpdate {
  return {
    code: v.code,
    name: v.name,
    address: normAddress(v.address),
    allows_issuance: v.allows_issuance,
    status: v.status,
  };
}
