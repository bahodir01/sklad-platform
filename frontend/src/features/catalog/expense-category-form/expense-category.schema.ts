import { z } from "zod";
import type { components } from "@/shared/api/schema";

type ExpenseCategoryCreate = components["schemas"]["ExpenseCategoryCreate"];
type ExpenseCategoryUpdate = components["schemas"]["ExpenseCategoryUpdate"];

/**
 * Значения формы вида расхода ДЕНЕГ (§8.5). Единый набор; create шлёт только
 * name (api.create у status=false), update — name+status. Лишний ключ в
 * билдере не скомпилируется против типа Create/Update.
 */
export const expenseCategoryFormSchema = z.object({
  name: z.string().min(1).max(100),
  status: z.enum(["active", "archived"]),
});

export type ExpenseCategoryFormValues = z.infer<typeof expenseCategoryFormSchema>;

/** create: только name. */
export function toExpenseCategoryCreate(v: ExpenseCategoryFormValues): ExpenseCategoryCreate {
  return { name: v.name };
}

/** update: name, status. */
export function toExpenseCategoryUpdate(v: ExpenseCategoryFormValues): ExpenseCategoryUpdate {
  return { name: v.name, status: v.status };
}
