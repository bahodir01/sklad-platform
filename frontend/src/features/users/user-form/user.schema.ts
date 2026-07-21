import { z } from "zod";
import type { components } from "@/shared/api/schema";

type UserCreate = components["schemas"]["UserCreate"];
type UserUpdate = components["schemas"]["UserUpdate"];

const ROLE_VALUES = ["admin", "teacher", "worker"] as const;
const CATEGORY_VALUES = ["teacher", "worker"] as const;

/**
 * INV-9 на клиенте (backend/app/modules/auth/schemas.py:_validate_inv9,
 * CHECK ck_users_category_iff_admin): category IS NULL ⟺ role = 'admin'.
 * Подсказка до отправки; итина всё равно проверяет сервер (§10 apply-api-error).
 */
function checkInv9(
  v: { role: (typeof ROLE_VALUES)[number]; category?: (typeof CATEGORY_VALUES)[number] },
  ctx: z.RefinementCtx,
): void {
  if (v.role === "admin" && v.category) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["category"],
      message: "Для роли «Администратор» категория не указывается",
    });
  }
  if (v.role !== "admin" && !v.category) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["category"],
      message: "Для ролей «Учитель» и «Работник» категория обязательна",
    });
  }
}

// email — формат проверяем всегда (если непусто); домен @npuu.uz настраивается
// на сервере (settings.email_domain) — жёсткую проверку домена на клиенте не
// дублируем, чтобы не разойтись при смене конфигурации; подсказка — в описании
// поля формы (UserFormFields), 422 email_wrong_domain — тостом с сервера.
const emailField = z
  .string()
  .max(255, "Не более 255 символов")
  .refine((v) => v.trim().length === 0 || z.string().email().safeParse(v.trim()).success, {
    message: "Введите корректный email",
  });

export const userCreateSchema = z
  .object({
    full_name: z.string().trim().min(1, "Обязательное поле").max(255),
    username: z
      .string()
      .trim()
      .min(1, "Обязательное поле")
      .max(150)
      .regex(/^\S+$/, "Логин не должен содержать пробелов"),
    email: emailField,
    role: z.enum(ROLE_VALUES),
    category: z.enum(CATEGORY_VALUES).optional(),
    password: z.string().min(8, "Минимум 8 символов").max(128),
  })
  .superRefine(checkInv9);

export type UserCreateFormValues = z.infer<typeof userCreateSchema>;

export const userUpdateSchema = z
  .object({
    full_name: z.string().trim().min(1, "Обязательное поле").max(255),
    email: emailField,
    role: z.enum(ROLE_VALUES),
    category: z.enum(CATEGORY_VALUES).optional(),
    is_active: z.boolean(),
  })
  .superRefine(checkInv9);

export type UserUpdateFormValues = z.infer<typeof userUpdateSchema>;

function normEmail(v: string): string | null {
  const t = v.trim();
  return t.length > 0 ? t : null;
}

/** Тело создания — ровно create-поля (§14): full_name, username, email, role,
 * category, password. category обнуляется для admin на клиенте до отправки —
 * зеркалит INV-9, финальную проверку всё равно делает схема/CHECK на сервере. */
export function toUserCreate(v: UserCreateFormValues): UserCreate {
  return {
    full_name: v.full_name,
    username: v.username,
    email: normEmail(v.email),
    role: v.role,
    category: v.role === "admin" ? null : (v.category ?? null),
    password: v.password,
  };
}

/** Тело правки — update-поля: full_name, email, role, category, is_active.
 * username не входит (api.update=false — логин не меняется, §14). */
export function toUserUpdate(v: UserUpdateFormValues): UserUpdate {
  return {
    full_name: v.full_name,
    email: normEmail(v.email),
    role: v.role,
    category: v.role === "admin" ? null : (v.category ?? null),
    is_active: v.is_active,
  };
}
