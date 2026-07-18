/**
 * Фабрика ключей Query (§7.2). Сегмент сущности = сегмент URL, чтобы ключ и
 * эндпоинт не разъехались. Иерархия неслучайна:
 * invalidate(['catalog', e]) накрывает все страницы, фильтры и детали разом.
 */

export type CatalogEntity =
  | "units"
  | "products"
  | "warehouses"
  | "expense-types"
  | "expense-categories";

export const catalogKeys = {
  all: (e: CatalogEntity) => ["catalog", e] as const,
  lists: (e: CatalogEntity) => ["catalog", e, "list"] as const,
  list: (e: CatalogEntity, params: Record<string, unknown>) =>
    ["catalog", e, "list", params] as const,
  detail: (e: CatalogEntity, id: number) => ["catalog", e, "detail", id] as const,
};

export const authKeys = {
  me: ["auth", "me"] as const,
};
