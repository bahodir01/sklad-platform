import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { documentKeys } from "@/shared/api/query-keys";
import type { Page } from "@/shared/api/types";
import type { NotificationListItem, NotificationRead } from "../model/types";

/** Список уведомлений: GET /notifications?page&size&status&warehouse_id (admin). */
export function useNotifications(params: {
  page: number;
  size: number;
  status?: string;
  warehouse_id?: number;
}) {
  return useQuery<Page<NotificationListItem>>({
    queryKey: documentKeys.notifications.list(params),
    queryFn: () => api.get<Page<NotificationListItem>>("/notifications", params),
    placeholderData: (prev) => prev,
  });
}

/** Деталь уведомления + строки с остатком к приобретению: GET /notifications/{id}. */
export function useNotification(id: number | null, enabled = true) {
  return useQuery<NotificationRead>({
    queryKey: documentKeys.notifications.detail(id ?? -1),
    queryFn: () => api.get<NotificationRead>(`/notifications/${id}`),
    enabled: enabled && id != null,
  });
}
