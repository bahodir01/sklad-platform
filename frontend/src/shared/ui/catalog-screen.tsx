import type { ReactNode } from "react";

interface CatalogScreenProps {
  title: string;
  /** Кнопка «Добавить» — только для canWrite (передаёт страница). */
  actions?: ReactNode;
  /** Фильтры — только реализованные в API (§1, Ф-5). */
  filters?: ReactNode;
  children: ReactNode;
  pagination?: ReactNode;
}

/**
 * Презентационный шелл экрана справочника — один шаблон на пять страниц (§9.2).
 * Ни useQuery, ни useMutation внутри: данные тянет страница-контейнер.
 */
export function CatalogScreen({ title, actions, filters, children, pagination }: CatalogScreenProps) {
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      {filters ? <div className="flex flex-wrap items-center gap-3">{filters}</div> : null}
      <div className="rounded-lg border">{children}</div>
      {pagination}
    </section>
  );
}
