import { z } from "zod";
import type { components } from "@/shared/api/schema";

type UnitCreate = components["schemas"]["UnitCreate"];
type UnitUpdate = components["schemas"]["UnitUpdate"];

/** Значения формы ЕИ (§8.1): code 1..16, name 1..100, is_active — только правка. */
export const unitFormSchema = z.object({
  code: z.string().min(1).max(16),
  name: z.string().min(1).max(100),
  is_active: z.boolean(),
});

export type UnitFormValues = z.infer<typeof unitFormSchema>;

/** create: code, name (is_active НЕ входит — api.create=false). */
export function toUnitCreate(v: UnitFormValues): UnitCreate {
  return { code: v.code, name: v.name };
}

/** update: code, name, is_active (архивация ЕИ). */
export function toUnitUpdate(v: UnitFormValues): UnitUpdate {
  return { code: v.code, name: v.name, is_active: v.is_active };
}
