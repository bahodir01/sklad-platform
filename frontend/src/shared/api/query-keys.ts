/**
 * Фабрика ключей Query (§7.2). Сегмент сущности = сегмент URL, чтобы ключ и
 * эндпоинт не разъехались. Иерархия неслучайна:
 * invalidate(['catalog', e]) накрывает все страницы, фильтры и детали разом.
 */

export type CatalogEntity =
  | "units"
  | "products"
  | "warehouses"
  | "expense-types"
  | "expense-categories";

export const catalogKeys = {
  all: (e: CatalogEntity) => ["catalog", e] as const,
  lists: (e: CatalogEntity) => ["catalog", e, "list"] as const,
  list: (e: CatalogEntity, params: Record<string, unknown>) =>
    ["catalog", e, "list", params] as const,
  detail: (e: CatalogEntity, id: number) => ["catalog", e, "detail", id] as const,
};

export const authKeys = {
  me: ["auth", "me"] as const,
};

// ── М2 Документы (§10, этап 2) ──────────────────────────────────────
export const documentKeys = {
  notifications: {
    all: ["documents", "notifications"] as const,
    lists: ["documents", "notifications", "list"] as const,
    list: (params: Record<string, unknown>) =>
      ["documents", "notifications", "list", params] as const,
    detail: (id: number) => ["documents", "notifications", "detail", id] as const,
  },
};

// ── М4 Заявки / очередь печати (§10, этап 3) ────────────────────────
export const requestKeys = {
  all: ["requests"] as const,
  my: (params: Record<string, unknown>) => ["requests", "my", params] as const,
  queue: (params: Record<string, unknown>) => ["requests", "queue", params] as const,
  detail: (id: number) => ["requests", "detail", id] as const,
  count: (status: string) => ["requests", "count", { status }] as const,
  registry: (params: Record<string, unknown>) => ["requests", "registry", params] as const,
};

// ── М5 Кассы (§10, этап 5) ──────────────────────────────────────────
export const cashKeys = {
  all: ["cash"] as const,
  desks: ["cash", "desks"] as const,
  myExpenses: (params: Record<string, unknown>) => ["cash", "expenses", "my", params] as const,
};

// ── М3 Остатки / движения (§10) ─────────────────────────────────────
export const stockKeys = {
  balances: (params: Record<string, unknown>) => ["stock", "balances", params] as const,
  movements: (params: Record<string, unknown>) => ["stock", "movements", params] as const,
};

// ── М6 Отчёты (§10, этап 6) ─────────────────────────────────────────
export const reportKeys = {
  balances: (params: Record<string, unknown>) => ["reports", "balances", params] as const,
  unpurchased: (params: Record<string, unknown>) => ["reports", "unpurchased", params] as const,
  movements: (params: Record<string, unknown>) => ["reports", "movements", params] as const,
  cashflow: (params: Record<string, unknown>) => ["reports", "cashflow", params] as const,
};
