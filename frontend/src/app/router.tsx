import { createBrowserRouter } from "react-router-dom";
import { RequireAuth } from "@/entities/session/ui/RequireAuth";
import { RequireRole } from "@/entities/session/ui/RequireRole";
import { AppLayout } from "./layouts/AppLayout";
import { AuthLayout } from "./layouts/AuthLayout";
import { LoginPage } from "@/pages/login/LoginPage";
import { RoleHome } from "@/pages/RoleHome";
import { UnitsPage } from "@/pages/catalog/UnitsPage";
import { ProductsPage } from "@/pages/catalog/ProductsPage";
import { WarehousesPage } from "@/pages/catalog/WarehousesPage";
import { ExpenseTypesPage } from "@/pages/catalog/ExpenseTypesPage";
import { ExpenseCategoriesPage } from "@/pages/catalog/ExpenseCategoriesPage";
import { MyRequestsPage } from "@/pages/requests/MyRequestsPage";
import { ToPrintPage } from "@/pages/requests/ToPrintPage";
import { RegistryPage } from "@/pages/requests/RegistryPage";
import { NotificationsPage } from "@/pages/documents/NotificationsPage";
import { AcquisitionsPage } from "@/pages/documents/AcquisitionsPage";
import { TransfersPage } from "@/pages/documents/TransfersPage";
import { WriteoffsPage } from "@/pages/documents/WriteoffsPage";
import { CashPage } from "@/pages/cash/CashPage";
import { CashExpensesPage } from "@/pages/cash/CashExpensesPage";
import { MyExpensesPage } from "@/pages/cash/MyExpensesPage";
import { ReportsPage } from "@/pages/reports/ReportsPage";
import { UsersPage } from "@/pages/users/UsersPage";
import { ForbiddenPage } from "@/pages/errors/ForbiddenPage";
import { NotFoundPage } from "@/pages/errors/NotFoundPage";
import { ROUTES } from "@/shared/config/routes";

/**
 * Карта роутинга по ролям (§5). Чтение справочников — любой аутентифицированный;
 * запись закрывает can(). Админские экраны (М2 документы, очередь «К печати»,
 * реестр, кассы-приход, отчёты) — под <RequireRole admin>; экраны сотрудника
 * («Мои заявки», «Мои расходы») — под <RequireRole teacher|worker>. Гвард роли
 * отдаёт /403 (не /login): «не твоя роль» ≠ «войди заново».
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
          { index: true, element: <RoleHome /> },

          // ── Справочники (М1): чтение любой ролью ──────────────────
          { path: ROUTES.catalog, element: <ProductsPage /> },
          { path: ROUTES.products, element: <ProductsPage /> },
          { path: ROUTES.units, element: <UnitsPage /> },
          { path: ROUTES.warehouses, element: <WarehousesPage /> },
          { path: ROUTES.expenseTypes, element: <ExpenseTypesPage /> },
          { path: ROUTES.expenseCategories, element: <ExpenseCategoriesPage /> },

          // ── Экраны сотрудника (teacher|worker) ────────────────────
          {
            element: <RequireRole roles={["teacher", "worker"]} />,
            children: [
              { path: ROUTES.myRequests, element: <MyRequestsPage /> },
              { path: ROUTES.myExpenses, element: <MyExpensesPage /> },
            ],
          },

          // ── Админские экраны (М2/М4/М5/М6) ────────────────────────
          {
            element: <RequireRole roles={["admin"]} />,
            children: [
              { path: ROUTES.toPrint, element: <ToPrintPage /> },
              { path: ROUTES.registry, element: <RegistryPage /> },
              { path: ROUTES.notifications, element: <NotificationsPage /> },
              { path: ROUTES.acquisitions, element: <AcquisitionsPage /> },
              { path: ROUTES.transfers, element: <TransfersPage /> },
              { path: ROUTES.writeoffs, element: <WriteoffsPage /> },
              { path: ROUTES.cash, element: <CashPage /> },
              { path: ROUTES.cashExpenses, element: <CashExpensesPage /> },
              { path: ROUTES.reports, element: <ReportsPage /> },
              { path: ROUTES.users, element: <UsersPage /> },
            ],
          },

          { path: ROUTES.forbidden, element: <ForbiddenPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
  },
]);
