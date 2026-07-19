import { useMemo } from "react";
import { useWarehousesForResolve } from "../api/queries";
import type { Warehouse } from "../model/types";

/**
 * Резолв склада по id для списков документов/заявок (хранится только
 * warehouse_id). Фолбэк «Склад #id», если вне первых 200.
 */
export function useWarehouseLookup() {
  const { data, isLoading } = useWarehousesForResolve();
  const map = useMemo(() => {
    const m = new Map<number, Warehouse>();
    for (const w of data?.items ?? []) m.set(w.id, w);
    return m;
  }, [data]);

  return {
    isLoading,
    get: (id: number): Warehouse | undefined => map.get(id),
    name: (id: number): string => {
      const w = map.get(id);
      return w ? `${w.code} — ${w.name}` : `Склад #${id}`;
    },
  };
}
