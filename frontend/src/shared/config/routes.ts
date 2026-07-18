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

  // ── Зарезервировано (этапы 2–6), НЕ строится на этапе 1 ──────────
  dashboard: "/dashboard",
  toPrint: "/to-print",
  notifications: "/notifications",
  acquisitions: "/acquisitions",
  transfers: "/transfers",
  writeoffs: "/writeoffs",
  stock: "/stock",
  cash: "/cash",
  reports: "/reports",
  myRequests: "/my/requests",
} as const;

/** Точка входа после логина. teacher/worker до этапа 3 идут туда же (Ф-4). */
export const HOME_ROUTE = ROUTES.products;
