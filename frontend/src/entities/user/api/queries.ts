import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { userKeys } from "@/shared/api/query-keys";
import type { Page } from "@/shared/api/types";
import type { User, UserRead } from "../model/types";

// type (не interface) — Record<string, unknown> в query-keys требует индексную
// сигнатуру, которую TS выводит структурно только для литеральных типов, не
// для именованных interface (тот же приём, что и в documentKeys/§10).
export type UsersQueryParams = {
  page: number;
  size: number;
  role?: string;
  is_active?: string;
  q?: string;
};

/** Список пользователей: GET /users?page&size&role&is_active&q (admin, §14). */
export function useUsers(params: UsersQueryParams) {
  return useQuery<Page<User>>({
    queryKey: userKeys.list(params),
    queryFn: () => api.get<Page<User>>("/users", params),
    // keepPreviousData: без него таблица мигает пустотой при смене страницы (§7.1).
    placeholderData: (prev) => prev,
  });
}

/** Деталь пользователя: GET /users/{id} (admin). Несёт created_at (get_single-only). */
export function useUser(id: number | null, enabled = true) {
  return useQuery<UserRead>({
    queryKey: userKeys.detail(id ?? -1),
    queryFn: () => api.get<UserRead>(`/users/${id}`),
    enabled: enabled && id != null,
  });
}
