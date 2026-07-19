import type { components } from "@/shared/api/schema";

/** М5 Кассы. Типы — из schema.d.ts (§2). */
export type CashDesk = components["schemas"]["CashDeskRead"];
export type CashDeskType = components["schemas"]["CashDeskType"];
export type MoneyIncomeCreate = components["schemas"]["MoneyIncomeCreate"];
export type MoneyIncomeRead = components["schemas"]["MoneyIncomeRead"];
export type MoneyExpenseListItem = components["schemas"]["MoneyExpenseList"];
export type MoneyExpenseRead = components["schemas"]["MoneyExpenseRead"];

/** Русские подписи типа кассы (= категория сотрудника, SV-6). */
export const CASH_DESK_LABEL: Record<CashDeskType, string> = {
  teacher: "Касса учителей",
  worker: "Касса работников",
};
