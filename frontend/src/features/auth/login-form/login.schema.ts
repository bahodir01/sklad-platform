import { z } from "zod";

/**
 * Границы — из DTO LoginRequest (1..150 / 1..128), НЕ из контракта users (§6).
 * users.username в словаре имеет 3..150 без пробелов — но это правило СОЗДАНИЯ
 * пользователя; навесив его на логин, мы сделали бы невходимой любую учётку с
 * коротким логином.
 */
export const loginSchema = z.object({
  username: z.string().min(1, "Введите логин").max(150),
  password: z.string().min(1, "Введите пароль").max(128),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
