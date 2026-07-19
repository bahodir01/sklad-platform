import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { cashKeys } from "@/shared/api/query-keys";
import type {
  ExpenseSubmitResult,
  MoneyIncomeCreate,
  MoneyIncomeRead,
  MoneyExpenseRead,
} from "../model/types";

/** Приход денег: POST /cash/income (ТОЛЬКО admin, §7.2). Обновляет балансы касс. */
export function useCreateIncome() {
  const qc = useQueryClient();
  return useMutation<MoneyIncomeRead, unknown, MoneyIncomeCreate>({
    mutationFn: (body) => api.post<MoneyIncomeRead>("/cash/income", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cashKeys.desks });
      qc.invalidateQueries({ queryKey: ["reports", "cashflow"] });
    },
  });
}

export interface ExpenseFormPayload {
  expense_category_id: number;
  amount: string;
  description: string;
  date: string;
  receipt: File;
}

/**
 * Расход денег с чеком: POST /cash/expenses (teacher/worker, multipart, §5.4).
 * Касса (cash_desk_id) и сотрудник (employee_id) — СЕРВЕР из JWT/категории
 * (SV-6): их в форме нет. Чек обязателен (INV-7).
 */
export function useCreateExpense() {
  const qc = useQueryClient();
  return useMutation<MoneyExpenseRead, unknown, ExpenseFormPayload>({
    mutationFn: (payload) => {
      const fd = new FormData();
      fd.append("expense_category_id", String(payload.expense_category_id));
      fd.append("amount", payload.amount);
      fd.append("description", payload.description);
      fd.append("date", payload.date);
      fd.append("receipt", payload.receipt);
      return api.postForm<MoneyExpenseRead>("/cash/expenses", fd);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cash", "expenses", "my"] });
      qc.invalidateQueries({ queryKey: cashKeys.desks });
      qc.invalidateQueries({ queryKey: ["reports", "cashflow"] });
    },
  });
}

/**
 * Передать расходы в бухгалтерию пачкой: POST
 * /cash/expenses/submit-to-accounting (admin, спека13 §4). У денег нет этапа
 * подписи — чек заменяет подпись. Общий submitted_register_no на весь вызов;
 * исключённые (снятая галочка) в список не попадают.
 */
export function useSubmitExpenses() {
  const qc = useQueryClient();
  return useMutation<ExpenseSubmitResult, unknown, number[]>({
    mutationFn: (ids) => api.post<ExpenseSubmitResult>("/cash/expenses/submit-to-accounting", { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cash", "expenses"] }),
  });
}
