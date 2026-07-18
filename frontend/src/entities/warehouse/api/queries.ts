import { useCatalogList, useCatalogDetail } from "@/shared/api/catalog-hooks";
import type { QueryValueMap } from "@/shared/api/catalog-crud";
import type { Warehouse, WarehouseRead } from "../model/types";

/** Список складов: GET /warehouses?page&size&status&allows_issuance (§10). */
export function useWarehouses(params: QueryValueMap) {
  return useCatalogList<Warehouse>("warehouses", params);
}

/**
 * Деталь склада: GET /warehouses/{id} (§10). ОБЯЗАТЕЛЬНА для правки — префилл из
 * строки таблицы невозможен, там нет address (get_index=false, К-H).
 */
export function useWarehouse(id: number | null, enabled = true) {
  return useCatalogDetail<WarehouseRead>("warehouses", id, enabled);
}
