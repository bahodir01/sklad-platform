import { api } from "./client";
import type { CatalogEntity } from "./query-keys";
import type { Page } from "./types";

export type QueryValueMap = Record<string, string | number | boolean | undefined>;

/**
 * Сырые CRUD-вызовы справочника (§10). path сегмент = сегмент URL = сегмент
 * ключа Query (units, products, warehouses, expense-types, expense-categories).
 * DELETE отсутствует — SV-8, его нет и на бэке.
 */
export function catalogApi<TList, TRead, TCreate, TUpdate>(entity: CatalogEntity) {
  const base = `/${entity}`;
  return {
    entity,
    list(params: QueryValueMap): Promise<Page<TList>> {
      return api.get<Page<TList>>(base, params);
    },
    get(id: number): Promise<TRead> {
      return api.get<TRead>(`${base}/${id}`);
    },
    create(body: TCreate): Promise<TRead> {
      return api.post<TRead>(base, body);
    },
    update(id: number, body: TUpdate): Promise<TRead> {
      return api.patch<TRead>(`${base}/${id}`, body);
    },
  };
}
