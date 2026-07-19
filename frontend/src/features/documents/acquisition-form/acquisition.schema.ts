import { z } from "zod";

/**
 * Схема приобретения (AcquisitionCreate контракта, admin, §6.2). Проводится на
 * основании уведомления: notification_id — из контекста, строки прогружаются из
 * остатка к приобретению. number/author_id — сервер. Контроль перезакупки
 * (SV-1/§4.2) — на сервере; его 422 показываем тостером.
 */
export const acquisitionItemSchema = z.object({
  product_id: z.number().int().positive(),
  qty: z.coerce
    .number({ invalid_type_error: "Введите количество" })
    .positive("Количество должно быть больше 0"),
  price: z.preprocess(
    (v) => (v === "" || v == null ? undefined : v),
    z.coerce.number({ invalid_type_error: "Число" }).min(0, "Цена не может быть отрицательной").optional(),
  ),
});

export const acquisitionSchema = z.object({
  date: z.string().min(1, "Укажите дату"),
  warehouse_id: z.number({ invalid_type_error: "Выберите склад" }).int().positive("Выберите склад"),
  supplier: z.string().max(255).optional(),
  items: z.array(acquisitionItemSchema).min(1, "Нет позиций к приобретению"),
});

export type AcquisitionFormValues = z.infer<typeof acquisitionSchema>;
