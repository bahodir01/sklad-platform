import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { documentKeys } from "@/shared/api/query-keys";
import type { NotificationCreate, NotificationRead } from "../model/types";

/** Создать уведомление: POST /notifications (admin). */
export function useCreateNotification() {
  const qc = useQueryClient();
  return useMutation<NotificationRead, unknown, NotificationCreate>({
    mutationFn: (body) => api.post<NotificationRead>("/notifications", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentKeys.notifications.all }),
  });
}
