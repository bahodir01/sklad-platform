import { z } from "zod";
import type { components } from "@/shared/api/schema";

type ProductCreate = components["schemas"]["ProductCreate"];
type ProductUpdate = components["schemas"]["ProductUpdate"];

/**
 * У товара create и update РАЗЛИЧАЮТСЯ составом (§8.2): unit_id есть только в
 * создании (api.update=false), status — только в правке. Поэтому две схемы.
 */
export const productCreateSchema = z.object({
  name: z.string().min(1).max(255),
  unit_id: z.number().int().refine((v) => v > 0, { message: "Выберите единицу измерения" }),
  sku: z.string().max(64),
});
export type ProductCreateValues = z.infer<typeof productCreateSchema>;

export const productUpdateSchema = z.object({
  name: z.string().min(1).max(255),
  sku: z.string().max(64),
  status: z.enum(["active", "archived"]),
});
export type ProductUpdateValues = z.infer<typeof productUpdateSchema>;

const normSku = (v: string): string | null => {
  const t = v.trim();
  return t.length > 0 ? t : null;
};

/** create: name, unit_id, sku. */
export function toProductCreate(v: ProductCreateValues): ProductCreate {
  return { name: v.name, unit_id: v.unit_id, sku: normSku(v.sku) };
}

/** update: name, sku, status (unit_id НЕ входит — api.update=false, К-E). */
export function toProductUpdate(v: ProductUpdateValues): ProductUpdate {
  return { name: v.name, sku: normSku(v.sku), status: v.status };
}
