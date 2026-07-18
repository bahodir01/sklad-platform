import { useCatalogList } from "@/shared/api/catalog-hooks";
import type { QueryValueMap } from "@/shared/api/catalog-crud";
import type { Unit } from "../model/types";

/** Список ЕИ: GET /units?page&size&is_active (§10). */
export function useUnits(params: QueryValueMap) {
  return useCatalogList<Unit>("units", params);
}

/**
 * Активные ЕИ для селекта товара: GET /units?is_active=true&size=200 (§10).
 * validations контракта: «выбор только из активных ЕИ».
 */
export function useActiveUnits() {
  return useCatalogList<Unit>("units", { is_active: true, size: 200, page: 1 });
}

/**
 * Все ЕИ для резолва названия в таблице товаров (§7.3, К-F): у products в списке
 * только unit_id (число). Включает архивные — товар мог ссылаться на такую.
 * Тот же префикс ключа ['catalog','units'] → инвалидация units→products
 * перерисует зависимую таблицу.
 */
export function useUnitsForResolve() {
  return useCatalogList<Unit>("units", { size: 200, page: 1 });
}
