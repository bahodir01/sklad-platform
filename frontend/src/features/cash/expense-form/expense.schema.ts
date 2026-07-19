import { z } from "zod";

/**
 * Схема расхода денег (teacher/worker, §5.4). Отправляется multipart с ФАЙЛОМ
 * чека. Касса (cash_desk_id) и сотрудник (employee_id) в форме ОТСУТСТВУЮТ —
 * сервер определяет их из категории/JWT (SV-6). Чек обязателен (INV-7).
 */
export const expenseSchema = z.object({
  expense_category_id: z
    .number({ invalid_type_error: "Выберите вид расхода" })
    .int()
    .positive("Выберите вид расхода"),
  amount: z.coerce.number({ invalid_type_error: "Введите сумму" }).positive("Сумма должна быть больше 0"),
  description: z.string().trim().min(1, "Опишите, на что потрачено"),
  date: z.string().min(1, "Укажите дату"),
  receipt: z.instanceof(File, { message: "Прикрепите чек" }),
});

export type ExpenseFormValues = z.infer<typeof expenseSchema>;
