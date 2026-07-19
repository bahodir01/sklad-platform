/**
 * Константы путей (§5). Этапы 2–6 зарезервированы здесь, чтобы не расползались
 * строковыми литералами; строятся не сейчас.
 */
export const ROUTES = {
  login: "/login",
  root: "/",

  catalog: "/catalog",
  products: "/catalog/products",
  units: "/catalog/units",
  warehouses: "/catalog/warehouses",
  expenseTypes: "/catalog/expense-types",
  expenseCategories: "/catalog/expense-categories",

  forbidden: "/403",

  // ── М4 Заявки / очередь печати (admin) + реестр ─────────────────
  toPrint: "/to-print",
  registry: "/registry",

  // ── М2 Документы (admin) ────────────────────────────────────────
  notifications: "/notifications",
  acquisitions: "/acquisitions",
  transfers: "/transfers",
  writeoffs: "/writeoffs", // admin: прямое списание порча/брак (§4.4)

  // ── М5 Кассы ────────────────────────────────────────────────────
  cash: "/cash", // admin: приход + балансы
  cashExpenses: "/cash/expenses-transfer", // admin: передача расходов в бухгалтерию (спека13 §5)
  myExpenses: "/my/expenses", // сотрудник: расход + свои расходы

  // ── М6 Отчёты (admin) ───────────────────────────────────────────
  reports: "/reports",

  // ── М4 Мои заявки (сотрудник) ───────────────────────────────────
  myRequests: "/my/requests",
} as const;

/** Точка входа после логина зависит от роли — вычисляется в <RoleHome/>. */
export const HOME_ROUTE = ROUTES.products;
