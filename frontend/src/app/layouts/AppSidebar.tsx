import { NavLink } from "react-router-dom";
import { cn } from "@/shared/lib/utils";
import { useMe } from "@/entities/session/api/use-me";
import { useRequestsCount } from "@/entities/request/api/queries";
import { NAV_SECTIONS, type NavItem } from "./nav-config";

/**
 * Боковая навигация (макет заказчика §9.1). Пункты фильтруются по роли текущего
 * пользователя (админские разделы сотруднику не показываются — это UX-слой над
 * серверным RBAC). Бейдж «К печати» — живой счётчик очереди (AP-3, refetch 30с),
 * запрашивается только у admin.
 */
export function AppSidebar({ collapsed }: { collapsed: boolean }) {
  const { data: me } = useMe();
  const role = me?.role;
  const isAdmin = role === "admin";
  const toPrintCount = useRequestsCount(isAdmin).data?.count ?? 0;

  const visible = (item: NavItem): boolean =>
    item.roles === undefined || (role != null && item.roles.includes(role));

  const badgeFor = (item: NavItem): number | undefined =>
    item.badgeKey === "toPrint" ? toPrintCount : undefined;

  return (
    <aside
      className={cn(
        "sticky top-0 flex h-screen flex-col border-r border-border bg-card",
        collapsed ? "w-[64px]" : "w-[240px]",
      )}
    >
      {/* Бренд */}
      <div className="flex h-14 items-center gap-2.5 border-b border-border px-4">
        <div className="grid h-8 w-8 flex-none place-items-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
          С
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold leading-tight">Складской учёт</div>
            <div className="text-[10.5px] uppercase tracking-wide text-muted-foreground">
              {isAdmin ? "Админ-панель" : "Рабочее место"}
            </div>
          </div>
        )}
      </div>

      {/* Навигация */}
      <nav className="flex-1 overflow-y-auto p-2.5" aria-label="Основная навигация">
        {NAV_SECTIONS.map((section, si) => {
          const items = section.items.filter(visible);
          if (items.length === 0) return null;
          return (
            <div key={section.title ?? `top-${si}`} className="mb-1">
              {section.title && !collapsed && (
                <div className="px-2.5 pb-1 pt-3 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {section.title}
                </div>
              )}
              {items.map((item) => {
                const Icon = item.icon;
                const badge = badgeFor(item);
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    title={collapsed ? item.label : undefined}
                    className={({ isActive }) =>
                      cn(
                        "mb-0.5 flex items-center gap-2.5 rounded-md px-2.5 py-[7px] text-[13px] font-medium transition-colors",
                        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                        isActive
                          ? "bg-brand-soft text-brand-text"
                          : "text-muted-foreground hover:bg-accent hover:text-foreground",
                      )
                    }
                  >
                    <Icon className="h-4 w-4 flex-none opacity-90" aria-hidden="true" />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                    {!collapsed && badge != null && badge > 0 && (
                      <span
                        className="ml-auto grid h-[19px] min-w-[19px] place-items-center rounded-full bg-warning px-1.5 text-[11px] font-bold tabular-nums text-warning-foreground"
                        aria-label={`${badge} в очереди`}
                      >
                        {badge}
                      </span>
                    )}
                  </NavLink>
                );
              })}
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
