import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { cashKeys } from "@/shared/api/query-keys";
import type { Page } from "@/shared/api/types";
import type {
  CashDesk,
  ExpenseRegistryRow,
  MoneyExpenseListItem,
} from "../model/types";

/** Балансы касс: GET /cash/desks (любая роль). Ответ — массив, не Page. */
export function useCashDesks(enabled = true) {
  return useQuery<CashDesk[]>({
    queryKey: cashKeys.desks,
    queryFn: () => api.get<CashDesk[]>("/cash/desks"),
    enabled,
  });
}

/** Мои расходы: GET /cash/expenses/my (teacher/worker, row-level §1.3). */
export function useMyExpenses(params: { page: number; size: number }) {
  return useQuery<Page<MoneyExpenseListItem>>({
    queryKey: cashKeys.myExpenses(params),
    queryFn: () => api.get<Page<MoneyExpenseListItem>>("/cash/expenses/my", params),
    placeholderData: (prev) => prev,
  });
}

/**
 * Расходы для передачи в бухгалтерию: GET /cash/expenses?submitted= (admin,
 * спека13 §5). Фильтр «Передано / Не передано». У денег нет этапа подписи —
 * расход готов к передаче сразу после проведения.
 */
export function useExpenses(params: { submitted: boolean; page: number; size: number }) {
  return useQuery<Page<MoneyExpenseListItem>>({
    queryKey: cashKeys.expenses(params),
    queryFn: () => api.get<Page<MoneyExpenseListItem>>("/cash/expenses", params),
    placeholderData: (prev) => prev,
  });
}

/** Реестр передачи денег: GET /cash/expenses/registry (admin, спека13 §4). */
export function useExpensesRegistry(
  params: { page: number; size: number; register_no?: string; date?: string },
  enabled = true,
) {
  return useQuery<Page<ExpenseRegistryRow>>({
    queryKey: cashKeys.expensesRegistry(params),
    queryFn: () => api.get<Page<ExpenseRegistryRow>>("/cash/expenses/registry", params),
    placeholderData: (prev) => prev,
    enabled,
  });
}
