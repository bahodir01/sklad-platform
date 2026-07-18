import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { catalogApi, type QueryValueMap } from "./catalog-crud";
import { catalogKeys, type CatalogEntity } from "./query-keys";
import type { Page } from "./types";

/**
 * Обобщённые хуки CRUD справочника — инкапсулируют инвалидацию (§7.3), чтобы
 * пять справочников не дублировали её и не расходились. Типы задаёт каждая
 * сущность в своих queries.ts/mutations.ts.
 */

export function useCatalogList<TList>(entity: CatalogEntity, params: QueryValueMap) {
  const client = catalogApi<TList, unknown, unknown, unknown>(entity);
  return useQuery<Page<TList>>({
    queryKey: catalogKeys.list(entity, params),
    queryFn: () => client.list(params),
    // keepPreviousData: без него таблица мигает пустотой при смене страницы (§7.1).
    placeholderData: (prev) => prev,
  });
}

export function useCatalogDetail<TRead>(
  entity: CatalogEntity,
  id: number | null,
  enabled = true,
) {
  const client = catalogApi<unknown, TRead, unknown, unknown>(entity);
  return useQuery<TRead>({
    queryKey: catalogKeys.detail(entity, id ?? -1),
    queryFn: () => client.get(id as number),
    enabled: enabled && id != null,
  });
}

export function useCreateCatalog<TRead, TCreate>(entity: CatalogEntity) {
  const qc = useQueryClient();
  const client = catalogApi<unknown, TRead, TCreate, unknown>(entity);
  return useMutation<TRead, unknown, TCreate>({
    mutationFn: (body) => client.create(body),
    onSuccess: () => {
      // Создание: инвалидируем всё дерево сущности (§7.3).
      qc.invalidateQueries({ queryKey: catalogKeys.all(entity) });
    },
  });
}

export function useUpdateCatalog<TRead extends { id: number }, TUpdate>(entity: CatalogEntity) {
  const qc = useQueryClient();
  const client = catalogApi<unknown, TRead, unknown, TUpdate>(entity);
  return useMutation<TRead, unknown, { id: number; body: TUpdate }>({
    mutationFn: ({ id, body }) => client.update(id, body),
    onSuccess: (data) => {
      // PATCH возвращает полный XRead → в деталь без лишнего GET; списки
      // инвалидируем (запись могла уехать/приехать под текущий фильтр).
      qc.setQueryData(catalogKeys.detail(entity, data.id), data);
      qc.invalidateQueries({ queryKey: catalogKeys.lists(entity) });
      // Единственная межсущностная связка этапа 1: units → products (§7.3, К-F).
      // Таблица товаров резолвит код ЕИ из кэша units — переименование ЕИ
      // обязано её перерисовать.
      if (entity === "units") {
        qc.invalidateQueries({ queryKey: catalogKeys.all("products") });
      }
    },
  });
}
