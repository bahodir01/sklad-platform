import { z } from "zod";
import type { components } from "@/shared/api/schema";

type ExpenseTypeCreate = components["schemas"]["ExpenseTypeCreate"];
type ExpenseTypeUpdate = components["schemas"]["ExpenseTypeUpdate"];

/**
 * Значения формы типа расхода товара (§8.4). requires_employee — z.boolean() БЕЗ
 * .refine(v=>v===true): required здесь = «обязано присутствовать в payload», а
 * не «должно быть отмечено» (для «Порчи»/«Брака» — false, К-B).
 */
export const expenseTypeFormSchema = z.object({
  name: z.string().min(1).max(100),
  requires_employee: z.boolean(),
  status: z.enum(["active", "archived"]),
});

export type ExpenseTypeFormValues = z.infer<typeof expenseTypeFormSchema>;

/** create: name, requires_employee. */
export function toExpenseTypeCreate(v: ExpenseTypeFormValues): ExpenseTypeCreate {
  return { name: v.name, requires_employee: v.requires_employee };
}

/** update: name, requires_employee, status. */
export function toExpenseTypeUpdate(v: ExpenseTypeFormValues): ExpenseTypeUpdate {
  return { name: v.name, requires_employee: v.requires_employee, status: v.status };
}
