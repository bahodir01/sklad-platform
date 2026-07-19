import { useMemo } from "react";
import { useProductsForResolve } from "../api/queries";
import type { Product } from "../model/types";

/**
 * Резолв товара по id для таблиц документов/заявок (строки хранят только
 * product_id). Возвращает функцию name(id) с фолбэком «Товар #id», если товар
 * вне первых 200 (см. отчёт, ограничение по резолву).
 */
export function useProductLookup() {
  const { data, isLoading } = useProductsForResolve();
  const map = useMemo(() => {
    const m = new Map<number, Product>();
    for (const p of data?.items ?? []) m.set(p.id, p);
    return m;
  }, [data]);

  return {
    isLoading,
    get: (id: number): Product | undefined => map.get(id),
    name: (id: number): string => map.get(id)?.name ?? `Товар #${id}`,
  };
}
