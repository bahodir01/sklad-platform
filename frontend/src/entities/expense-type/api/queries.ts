import { useCatalogList } from "@/shared/api/catalog-hooks";
import type { QueryValueMap } from "@/shared/api/catalog-crud";
import type { ExpenseType } from "../model/types";

/** Список типов расхода товара: GET /expense-types?page&size&status (§10). */
export function useExpenseTypes(params: QueryValueMap) {
  return useCatalogList<ExpenseType>("expense-types", params);
}
