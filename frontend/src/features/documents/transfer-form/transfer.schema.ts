import { z } from "zod";

/**
 * Схема перемещения (TransferCreate контракта, admin, §6.3). Источник → получатель
 * + строки. number/author_id — сервер; проводка делает две записи ledger (SV-3).
 * Склад-получатель обязан отличаться от источника (иначе перемещение бессмысленно
 * и его отверг бы сервер).
 */
export const transferItemSchema = z.object({
  product_id: z.number({ invalid_type_error: "Выберите товар" }).int().positive("Выберите товар"),
  qty: z.coerce
    .number({ invalid_type_error: "Введите количество" })
    .positive("Количество должно быть больше 0"),
});

export const transferSchema = z
  .object({
    date: z.string().min(1, "Укажите дату"),
    from_warehouse_id: z
      .number({ invalid_type_error: "Выберите склад" })
      .int()
      .positive("Выберите склад-источник"),
    to_warehouse_id: z
      .number({ invalid_type_error: "Выберите склад" })
      .int()
      .positive("Выберите склад-получатель"),
    items: z.array(transferItemSchema).min(1, "Добавьте хотя бы одну позицию"),
  })
  .refine((v) => v.from_warehouse_id !== v.to_warehouse_id, {
    message: "Склад-получатель должен отличаться от источника",
    path: ["to_warehouse_id"],
  });

export type TransferFormValues = z.infer<typeof transferSchema>;
