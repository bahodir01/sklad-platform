import { createBrowserRouter, Navigate } from "react-router-dom";
import { RequireAuth } from "@/entities/session/ui/RequireAuth";
import { AppLayout } from "./layouts/AppLayout";
import { AuthLayout } from "./layouts/AuthLayout";
import { LoginPage } from "@/pages/login/LoginPage";
import { UnitsPage } from "@/pages/catalog/UnitsPage";
import { ProductsPage } from "@/pages/catalog/ProductsPage";
import { WarehousesPage } from "@/pages/catalog/WarehousesPage";
import { ExpenseTypesPage } from "@/pages/catalog/ExpenseTypesPage";
import { ExpenseCategoriesPage } from "@/pages/catalog/ExpenseCategoriesPage";
import { ForbiddenPage } from "@/pages/errors/ForbiddenPage";
import { NotFoundPage } from "@/pages/errors/NotFoundPage";
import { StubPage } from "@/pages/stub/StubPage";
import { ROUTES, HOME_ROUTE } from "@/shared/config/routes";

/** Заглушки этапов 2–6: показаны в меню, ведут сюда (строятся не на этапе 1). */
const STUBS: { path: string; title: string }[] = [
  { path: ROUTES.dashboard, title: "Дашборд" },
  { path: ROUTES.toPrint, title: "К печати" },
  { path: ROUTES.notifications, title: "Уведомления" },
  { path: ROUTES.acquisitions, title: "Приобретения" },
  { path: ROUTES.transfers, title: "Перемещения" },
  { path: ROUTES.writeoffs, title: "Расходы товара" },
  { path: ROUTES.stock, title: "Остатки" },
  { path: `${ROUTES.stock}/movements`, title: "Движения" },
  { path: ROUTES.cash, title: "Кассы" },
  { path: ROUTES.reports, title: "Отчёты" },
  { path: ROUTES.myRequests, title: "Мои заявки" },
];

/**
 * Карта роутинга (§5). Все экраны М1 — под RequireAuth (чтение любой ролью,
 * запись закрывает can()). RequireRole на этапе 1 не используется маршрутами.
 */
export const router = createBrowserRouter([
  {
    element: <AuthLayout />,
    children: [{ path: ROUTES.login, element: <LoginPage /> }],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <Navigate to={HOME_ROUTE} replace /> },
          { path: ROUTES.catalog, element: <Navigate to={ROUTES.products} replace /> },
          { path: ROUTES.products, element: <ProductsPage /> },
          { path: ROUTES.units, element: <UnitsPage /> },
          { path: ROUTES.warehouses, element: <WarehousesPage /> },
          { path: ROUTES.expenseTypes, element: <ExpenseTypesPage /> },
          { path: ROUTES.expenseCategories, element: <ExpenseCategoriesPage /> },
          { path: ROUTES.forbidden, element: <ForbiddenPage /> },
          ...STUBS.map((s) => ({ path: s.path, element: <StubPage title={s.title} /> })),
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
