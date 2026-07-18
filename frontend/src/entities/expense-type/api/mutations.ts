import { useCreateCatalog, useUpdateCatalog } from "@/shared/api/catalog-hooks";
import type { ExpenseTypeCreate, ExpenseTypeRead, ExpenseTypeUpdate } from "../model/types";

export function useCreateExpenseType() {
  return useCreateCatalog<ExpenseTypeRead, ExpenseTypeCreate>("expense-types");
}

export function useUpdateExpenseType() {
  return useUpdateCatalog<ExpenseTypeRead, ExpenseTypeUpdate>("expense-types");
}
