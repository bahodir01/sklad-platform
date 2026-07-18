import { Outlet } from "react-router-dom";
import { useUiStore } from "@/shared/model/ui-store";
import { AppSidebar } from "./AppSidebar";
import { AppHeader } from "./AppHeader";

/**
 * Каркас приложения (§9.1): Sidebar + Header + <Outlet/>. Плотная сетка макета
 * заказчика. Skip-link ведёт на <main> (доступность §11).
 */
export function AppLayout() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);

  return (
    <div className="flex min-h-screen bg-background">
      <a href="#main-content" className="skip-link">
        Перейти к содержимому
      </a>
      <AppSidebar collapsed={collapsed} />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader onToggleSidebar={toggle} />
        <main id="main-content" className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
