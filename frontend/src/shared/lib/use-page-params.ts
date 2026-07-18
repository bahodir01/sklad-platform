import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

/**
 * Фильтры и страница — в URL, не в сторе (Ф-1). Фильтр — вход в ключ Query;
 * в URL он шарится ссылкой, переживает F5 и «назад», не рассинхронится со стором.
 */

const DEFAULT_SIZE = 50;

export interface PageState {
  page: number;
  size: number;
}

export function usePageParams() {
  const [searchParams, setSearchParams] = useSearchParams();

  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const size = Math.max(1, Number(searchParams.get("size")) || DEFAULT_SIZE);

  const api = useMemo(
    () => ({
      get(key: string): string | undefined {
        return searchParams.get(key) ?? undefined;
      },
      /** Установить фильтр и сбросить страницу на 1 (иначе окажемся вне диапазона). */
      setFilter(key: string, value: string | undefined) {
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          if (value === undefined || value === "") next.delete(key);
          else next.set(key, value);
          next.delete("page");
          return next;
        });
      },
      setPage(nextPage: number) {
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          if (nextPage <= 1) next.delete("page");
          else next.set("page", String(nextPage));
          return next;
        });
      },
    }),
    [searchParams, setSearchParams],
  );

  return { page, size, ...api };
}
