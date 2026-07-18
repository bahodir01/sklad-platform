import { Search, Moon, Sun, PanelLeft } from "lucide-react";
import { useMe } from "@/entities/session/api/use-me";
import { LogoutButton } from "@/features/auth/logout-button/LogoutButton";
import { roleLabel } from "@/shared/config/roles";
import { Button } from "@/shared/ui/button";
import { useTheme } from "@/app/providers/ThemeProvider";

function initials(fullName: string | undefined): string {
  if (!fullName) return "?";
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  return (parts[0]?.[0] ?? "").concat(parts[1]?.[0] ?? "").toUpperCase() || "?";
}

/**
 * Верхняя панель (макет заказчика §9.1): переключатель сайдбара, поиск,
 * переключатель темы, пользователь + выход. Поиск на этапе 1 отключён — API не
 * принимает name__icontains (К-C, Ф-5); включится параметром `q` на бэке.
 */
export function AppHeader({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const { data: me } = useMe();
  const { resolved, toggle } = useTheme();

  return (
    <header className="sticky top-0 z-10 flex h-14 items-center gap-4 border-b border-border bg-card px-4">
      <Button
        variant="ghost"
        size="icon"
        onClick={onToggleSidebar}
        aria-label="Свернуть/развернуть меню"
      >
        <PanelLeft className="h-4 w-4" />
      </Button>

      <div className="relative w-full max-w-md">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <input
          type="search"
          disabled
          title="Поиск появится после подключения фильтров на бэкенде"
          placeholder="Поиск (в разработке)…"
          className="h-9 w-full rounded-md border border-input bg-secondary/60 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground disabled:cursor-not-allowed"
          aria-label="Поиск"
        />
      </div>

      <div className="ml-auto flex items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          onClick={toggle}
          aria-label={resolved === "dark" ? "Светлая тема" : "Тёмная тема"}
        >
          {resolved === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>

        <div className="flex items-center gap-2.5 pl-1">
          <div className="grid h-8 w-8 flex-none place-items-center rounded-full bg-primary text-[13px] font-semibold text-primary-foreground">
            {initials(me?.full_name)}
          </div>
          <div className="hidden leading-tight sm:block">
            <div className="text-[12.5px] font-medium">{me?.full_name ?? "—"}</div>
            <div className="text-[11px] text-muted-foreground">
              {me ? roleLabel(me.role) : ""}
            </div>
          </div>
        </div>

        <LogoutButton />
      </div>
    </header>
  );
}
