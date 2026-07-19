import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { cashKeys } from "@/shared/api/query-keys";
import type { Page } from "@/shared/api/types";
import type { CashDesk, MoneyExpenseListItem } from "../model/types";

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
