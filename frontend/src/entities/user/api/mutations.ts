import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { authKeys, userKeys } from "@/shared/api/query-keys";
import type { UserCreate, UserRead, UserUpdate } from "../model/types";

/** Создать пользователя: POST /users (admin, §14). */
export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation<UserRead, unknown, UserCreate>({
    mutationFn: (body) => api.post<UserRead>("/users", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}

/**
 * Правка пользователя: PATCH /users/{id} (full_name/email/role/category/is_active).
 * PATCH возвращает полный UserRead → в деталь без лишнего GET; списки инвалидируем
 * (запись могла уехать/приехать под текущий фильтр role/is_active). Если правили
 * себя — шапка (ФИО/роль) читает ['auth','me'], поэтому его тоже инвалидируем.
 */
export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation<UserRead, unknown, { id: number; body: UserUpdate }>({
    mutationFn: ({ id, body }) => api.patch<UserRead>(`/users/${id}`, body),
    onSuccess: (data) => {
      qc.setQueryData(userKeys.detail(data.id), data);
      qc.invalidateQueries({ queryKey: userKeys.lists });
      qc.invalidateQueries({ queryKey: authKeys.me });
    },
  });
}

/**
 * Сброс пароля: POST /users/{id}/reset-password → 204 (admin, §14). Гасит все
 * refresh-сессии пользователя в Redis на сервере; на клиенте — просто тост.
 */
export function useResetPassword() {
  return useMutation<void, unknown, { id: number; password: string }>({
    mutationFn: ({ id, password }) => api.post<void>(`/users/${id}/reset-password`, { password }),
  });
}
