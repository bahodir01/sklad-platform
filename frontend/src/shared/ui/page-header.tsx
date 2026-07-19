import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  /** Хлебные крошки: «Документы › Уведомления». */
  breadcrumb?: string;
  actions?: ReactNode;
}

/**
 * Шапка страницы (макет заказчика): breadcrumb + h1 + подзаголовок + действия
 * справа. Один h1 на страницу (§11).
 */
export function PageHeader({ title, subtitle, breadcrumb, actions }: PageHeaderProps) {
  return (
    <div className="mb-5">
      {breadcrumb ? (
        <p className="mb-1 text-xs text-muted-foreground">{breadcrumb}</p>
      ) : null}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
    </div>
  );
}
