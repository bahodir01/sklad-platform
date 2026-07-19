import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { requestKeys } from "@/shared/api/query-keys";
import type {
  BatchPrintResult,
  IssueResult,
  RequestCreate,
  RequestRead,
} from "../model/types";

/** Создать заявку (черновик): POST /requests (teacher/worker). */
export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation<RequestRead, unknown, RequestCreate>({
    mutationFn: (body) => api.post<RequestRead>("/requests", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: requestKeys.all }),
  });
}

/** Подтвердить заявку (draft→to_print): POST /requests/{id}/confirm (владелец). */
export function useConfirmRequest() {
  const qc = useQueryClient();
  return useMutation<RequestRead, unknown, number>({
    mutationFn: (id) => api.post<RequestRead>(`/requests/${id}/confirm`),
    onSuccess: () => qc.invalidateQueries({ queryKey: requestKeys.all }),
  });
}

/** Отметить напечатанной (to_print→printed): POST /requests/{id}/print (admin). */
export function usePrintRequest() {
  const qc = useQueryClient();
  return useMutation<RequestRead, unknown, number>({
    mutationFn: (id) => api.post<RequestRead>(`/requests/${id}/print`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: requestKeys.all });
    },
  });
}

/**
 * Выдать (printed→issued): POST /requests/{id}/issue (admin). Idempotency-Key
 * гасит двойной клик/ретрай (§6). Инвалидирует остатки и очередь.
 */
export function useIssueRequest() {
  const qc = useQueryClient();
  return useMutation<IssueResult, unknown, number>({
    mutationFn: (id) =>
      api.post<IssueResult>(`/requests/${id}/issue`, undefined, {
        // Idempotency-Key гасит двойной клик/ретрай сети до входа в транзакцию
        // (§6, CORS разрешает заголовок — main.py:49).
        headers: { "Idempotency-Key": `issue-${id}-${crypto.randomUUID()}` },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: requestKeys.all });
      qc.invalidateQueries({ queryKey: ["stock"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

/** Пакетная печать очереди: POST /requests/batch-print (admin). */
export function useBatchPrint() {
  const qc = useQueryClient();
  return useMutation<BatchPrintResult, unknown, number[]>({
    mutationFn: (ids) => api.post<BatchPrintResult>("/requests/batch-print", { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: requestKeys.all }),
  });
}
