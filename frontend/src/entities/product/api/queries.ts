import { useCatalogList } from "@/shared/api/catalog-hooks";
import type { QueryValueMap } from "@/shared/api/catalog-crud";
import type { Product } from "../model/types";

/** Список товаров: GET /products?page&size&status&unit_id (§10). */
export function useProducts(params: QueryValueMap) {
  return useCatalogList<Product>("products", params);
}

/**
 * Активные товары для селектов документов/заявок (choice_model контракта
 * `GET /products?status=active`). size=200 покрывает справочник проекта.
 */
export function useActiveProducts() {
  return useCatalogList<Product>("products", { status: "active", size: 200, page: 1 });
}

/**
 * Все товары для резолва названия по product_id (строки документов хранят только
 * id; §7.3 аналог units→products). Тот же префикс ключа ['catalog','products'].
 */
export function useProductsForResolve() {
  return useCatalogList<Product>("products", { size: 200, page: 1 });
}
