import { useCatalogList } from "@/shared/api/catalog-hooks";
import type { QueryValueMap } from "@/shared/api/catalog-crud";
import type { ExpenseType } from "../model/types";

/** Список типов расхода товара: GET /expense-types?page&size&status (§10). */
export function useExpenseTypes(params: QueryValueMap) {
  return useCatalogList<ExpenseType>("expense-types", params);
}

/**
 * Активные типы расхода товара для селектов (choice_model
 * `GET /expense-types?status=active`). Фильтрация по requires_employee — на
 * клиенте: API этого фильтра не принимает (см. §1 архитектуры, К-C).
 */
export function useActiveExpenseTypes() {
  return useExpenseTypes({ status: "active", size: 200, page: 1 });
}
