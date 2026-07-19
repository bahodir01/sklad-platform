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

/** Активные склады для селекта уведомления (choice_model `GET /warehouses?status=active`). */
export function useActiveWarehouses() {
  return useCatalogList<Warehouse>("warehouses", { status: "active", size: 200, page: 1 });
}

/**
 * Склады списания для формы заявки: allows_issuance=true AND status=active
 * (AP-12, SV-9). Сотрудник подаёт заявку только с такого склада.
 */
export function useIssuanceWarehouses() {
  return useCatalogList<Warehouse>("warehouses", {
    allows_issuance: true,
    status: "active",
    size: 200,
    page: 1,
  });
}

/** Все склады для резолва названия по warehouse_id (списки документов/заявок). */
export function useWarehousesForResolve() {
  return useCatalogList<Warehouse>("warehouses", { size: 200, page: 1 });
}
