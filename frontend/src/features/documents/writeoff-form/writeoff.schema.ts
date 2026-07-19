import { z } from "zod";

/**
 * Схема прямого списания порча/брак (WriteoffCreate контракта, admin, §4.4).
 * Склад + тип расхода (только requires_employee=false) + строки товар/кол-во/
 * причина. employee_id НЕ входит: при порче/браке он обязан быть NULL (INV-4),
 * сервер это гарантирует. number/requires_employee/author_id ставит сервер.
 */
export const writeoffItemSchema = z.object({
  product_id: z.number({ invalid_type_error: "Выберите товар" }).int().positive("Выберите товар"),
  qty: z.coerce
    .number({ invalid_type_error: "Введите количество" })
    .positive("Количество должно быть больше 0"),
  reason: z.string().max(500, "Не длиннее 500 символов").optional(),
});

export const writeoffSchema = z.object({
  date: z.string().min(1, "Укажите дату"),
  warehouse_id: z
    .number({ invalid_type_error: "Выберите склад" })
    .int()
    .positive("Выберите склад"),
  expense_type_id: z
    .number({ invalid_type_error: "Выберите тип расхода" })
    .int()
    .positive("Выберите тип расхода"),
  items: z.array(writeoffItemSchema).min(1, "Добавьте хотя бы одну позицию"),
});

export type WriteoffFormValues = z.infer<typeof writeoffSchema>;
