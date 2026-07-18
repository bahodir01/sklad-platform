import { useCatalogList } from "@/shared/api/catalog-hooks";
import type { QueryValueMap } from "@/shared/api/catalog-crud";
import type { ExpenseCategory } from "../model/types";

/** Список видов расхода денег: GET /expense-categories?page&size&status (§10). */
export function useExpenseCategories(params: QueryValueMap) {
  return useCatalogList<ExpenseCategory>("expense-categories", params);
}
