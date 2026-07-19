import { z } from "zod";

/**
 * Схема уведомления (NotificationCreate контракта, admin, §6.1). Состав —
 * ровно create-поля: date, warehouse_id, division_name, body_text, comment?,
 * items[{product_id, qty_requested}]. number/author_id/status — сервер.
 */
export const notificationItemSchema = z.object({
  product_id: z.number({ invalid_type_error: "Выберите товар" }).int().positive("Выберите товар"),
  qty_requested: z.coerce
    .number({ invalid_type_error: "Введите количество" })
    .positive("Количество должно быть больше 0"),
});

export const notificationSchema = z.object({
  date: z.string().min(1, "Укажите дату"),
  warehouse_id: z.number({ invalid_type_error: "Выберите склад" }).int().positive("Выберите склад"),
  division_name: z.string().trim().min(1, "Укажите подразделение").max(255),
  body_text: z.string().trim().min(1, "Заполните текст обращения"),
  comment: z.string().optional(),
  items: z.array(notificationItemSchema).min(1, "Добавьте хотя бы одну позицию"),
});

export type NotificationFormValues = z.infer<typeof notificationSchema>;
