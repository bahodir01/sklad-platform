import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { requestKeys } from "@/shared/api/query-keys";
import type { Page } from "@/shared/api/types";
import type {
  RequestCount,
  RequestListItem,
  RegistryRow,
  RequestQueueStatus,
} from "../model/types";

/** Мои заявки: GET /requests/my (teacher/worker, row-level §1.3). */
export function useMyRequests(params: { page: number; size: number }) {
  return useQuery<Page<RequestListItem>>({
    queryKey: requestKeys.my(params),
    queryFn: () => api.get<Page<RequestListItem>>("/requests/my", params),
    placeholderData: (prev) => prev,
  });
}

/**
 * Заявки по статусу: GET /requests?status=... (admin, спека13 §5). Экран
 * «Выдачи товара» — журнал-трекер по 4 фильтрам: to_issue → issued → signed →
 * submitted. Каждый статус — свой набор строк и свои действия.
 */
export function useRequestsByStatus(
  status: RequestQueueStatus,
  params: { page: number; size: number },
  enabled = true,
) {
  return useQuery<Page<RequestListItem>>({
    queryKey: requestKeys.queue({ status, ...params }),
    queryFn: () => api.get<Page<RequestListItem>>("/requests", { status, ...params }),
    placeholderData: (prev) => prev,
    enabled,
  });
}

/**
 * Счётчик заявок в статусе: GET /requests/count?status=... (спека13 §5).
 * Кормит и бейдж в навигации, и карточки-фильтры экрана «Выдачи товара».
 */
export function useRequestsCount(status: RequestQueueStatus, enabled = true) {
  return useQuery<RequestCount>({
    queryKey: requestKeys.count(status),
    queryFn: () => api.get<RequestCount>("/requests/count", { status }),
    enabled,
    refetchInterval: 30_000,
  });
}

/**
 * Реестр ПЕРЕДАЧИ в бухгалтерию: GET /requests/registry (спека13 §4, ADR-2a).
 * Оба номера (заявки + проводки) + номер реестра передачи. Фильтр по
 * register_no/date — для перепечати конкретного реестра.
 */
export function useRegistry(
  params: { page: number; size: number; register_no?: string; date?: string },
  enabled = true,
) {
  return useQuery<Page<RegistryRow>>({
    queryKey: requestKeys.registry(params),
    queryFn: () => api.get<Page<RegistryRow>>("/requests/registry", params),
    placeholderData: (prev) => prev,
    enabled,
  });
}
