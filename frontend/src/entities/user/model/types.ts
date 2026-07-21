import type { components } from "@/shared/api/schema";

/** М7 «Пользователи» (ОВ-12). Типы — из schema.d.ts (§2), контракт users. */
export type User = components["schemas"]["UserList"];
export type UserRead = components["schemas"]["UserRead"];
export type UserCreate = components["schemas"]["UserCreate"];
export type UserUpdate = components["schemas"]["UserUpdate"];
export type PasswordResetIn = components["schemas"]["PasswordResetIn"];
