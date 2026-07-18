import { useCatalogList } from "@/shared/api/catalog-hooks";
import type { QueryValueMap } from "@/shared/api/catalog-crud";
import type { Product } from "../model/types";

/** Список товаров: GET /products?page&size&status&unit_id (§10). */
export function useProducts(params: QueryValueMap) {
  return useCatalogList<Product>("products", params);
}
