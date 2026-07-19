import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { requestKeys } from "@/shared/api/query-keys";
import type { Page } from "@/shared/api/types";
import type { RequestCount, RequestListItem, RegistryRow } from "../model/types";

/** Мои заявки: GET /requests/my (teacher/worker, row-level §1.3). */
export function useMyRequests(params: { page: number; size: number }) {
  return useQuery<Page<RequestListItem>>({
    queryKey: requestKeys.my(params),
    queryFn: () => api.get<Page<RequestListItem>>("/requests/my", params),
    placeholderData: (prev) => prev,
  });
}

/**
 * Заявки по статусу: GET /requests?status=... (admin, AP-2). Очередь печати
 * рисуется из двух наборов — to_print (кнопка «Печать») и printed (кнопка
 * «Выдано»): статичный GET /requests/{id} на бэке отсутствует, состав строк в
 * списке не отдаётся (RequestList без items) — см. отчёт, вопрос Q-2.
 */
export function useRequestsByStatus(
  status: "to_print" | "printed" | "issued" | "draft",
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

/** Счётчик очереди «К печати» для бейджа (AP-3), refetch каждые 30с. */
export function useRequestsCount(enabled: boolean) {
  return useQuery<RequestCount>({
    queryKey: requestKeys.count("to_print"),
    queryFn: () => api.get<RequestCount>("/requests/count", { status: "to_print" }),
    enabled,
    refetchInterval: 30_000,
  });
}

/** Реестр выданных: GET /requests/registry (оба номера, ADR-2a). */
export function useRegistry(params: { page: number; size: number }) {
  return useQuery<Page<RegistryRow>>({
    queryKey: requestKeys.registry(params),
    queryFn: () => api.get<Page<RegistryRow>>("/requests/registry", params),
    placeholderData: (prev) => prev,
  });
}
