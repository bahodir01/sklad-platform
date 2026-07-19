import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { documentKeys } from "@/shared/api/query-keys";
import type { NotificationCreate, NotificationRead, NotificationUpdate } from "../model/types";

/** Создать уведомление: POST /notifications (admin). */
export function useCreateNotification() {
  const qc = useQueryClient();
  return useMutation<NotificationRead, unknown, NotificationCreate>({
    mutationFn: (body) => api.post<NotificationRead>("/notifications", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.notifications.all }),
  });
}

/**
 * Отправить черновик в работу: POST /notifications/{id}/submit (draft → in_progress,
 * ОВ-11, ручной submit завскладом). Инвалидируем весь префикс — накрывает и список,
 * и деталь.
 */
export function useSubmitNotification() {
  const qc = useQueryClient();
  return useMutation<NotificationRead, unknown, number>({
    mutationFn: (id) => api.post<NotificationRead>(`/notifications/${id}/submit`),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.notifications.all }),
  });
}

/**
 * Редактировать уведомление: PATCH /notifications/{id} (SV-10). Гейтинг по статусу —
 * UX-слой; сервер проверяет всё равно. Инвалидация — список + деталь (префикс `all`).
 */
export function useUpdateNotification() {
  const qc = useQueryClient();
  return useMutation<NotificationRead, unknown, { id: number; body: NotificationUpdate }>({
    mutationFn: ({ id, body }) => api.patch<NotificationRead>(`/notifications/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.notifications.all }),
  });
}

/**
 * Удалить уведомление: DELETE /notifications/{id} (SV-11 — только когда нет
 * приобретений; сервер защищён FK ondelete=RESTRICT). Инвалидация — список + деталь.
 */
export function useDeleteNotification() {
  const qc = useQueryClient();
  return useMutation<void, unknown, number>({
    mutationFn: (id) => api.del(`/notifications/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.notifications.all }),
  });
}
