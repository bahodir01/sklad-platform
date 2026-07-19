import { z } from "zod";

/**
 * Схема прихода в кассу (MoneyIncomeCreate контракта, ТОЛЬКО admin, §7.2).
 * author_id — сервер из JWT (api.create=false). Касса выбирается явно (в отличие
 * от расхода, где её определяет сервер по категории сотрудника).
 */
export const incomeSchema = z.object({
  cash_desk_id: z.number({ invalid_type_error: "Выберите кассу" }).int().positive("Выберите кассу"),
  amount: z.coerce.number({ invalid_type_error: "Введите сумму" }).positive("Сумма должна быть больше 0"),
  date: z.string().min(1, "Укажите дату"),
  comment: z.string().max(500).optional(),
});

export type IncomeFormValues = z.infer<typeof incomeSchema>;
