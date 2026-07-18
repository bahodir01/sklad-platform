import { useCreateCatalog, useUpdateCatalog } from "@/shared/api/catalog-hooks";
import type {
  ExpenseCategoryCreate,
  ExpenseCategoryRead,
  ExpenseCategoryUpdate,
} from "../model/types";

export function useCreateExpenseCategory() {
  return useCreateCatalog<ExpenseCategoryRead, ExpenseCategoryCreate>("expense-categories");
}

export function useUpdateExpenseCategory() {
  return useUpdateCatalog<ExpenseCategoryRead, ExpenseCategoryUpdate>("expense-categories");
}
