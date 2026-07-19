import { z } from "zod";

/**
 * Схема заявки (RequestCreate контракта): warehouse_id, reason, items[].
 * employee_id НЕ входит — сервер ставит из JWT (api.create=false, SV-6-аналог).
 * warehouse_id — только склад списания (AP-12), опции фильтрует форма.
 */
export const requestItemSchema = z.object({
  product_id: z
    .number({ invalid_type_error: "Выберите товар" })
    .int()
    .positive("Выберите товар"),
  qty: z
    .number({ invalid_type_error: "Введите количество" })
    .positive("Количество должно быть больше 0"),
});

export const requestSchema = z.object({
  warehouse_id: z
    .number({ invalid_type_error: "Выберите склад" })
    .int()
    .positive("Выберите склад"),
  reason: z.string().trim().min(1, "Укажите причину получения"),
  items: z.array(requestItemSchema).min(1, "Добавьте хотя бы одну позицию"),
});

export type RequestFormValues = z.infer<typeof requestSchema>;
