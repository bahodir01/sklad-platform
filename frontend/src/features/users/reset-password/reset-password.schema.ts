import { z } from "zod";

/** Тело POST /users/{id}/reset-password (§14 backend: PasswordResetIn, min 8). */
export const resetPasswordSchema = z
  .object({
    password: z.string().min(8, "Минимум 8 символов").max(128),
    confirm: z.string().min(1, "Обязательное поле"),
  })
  .refine((v) => v.password === v.confirm, {
    message: "Пароли не совпадают",
    path: ["confirm"],
  });

export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;
