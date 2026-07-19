import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { requestKeys } from "@/shared/api/query-keys";
import type {
  BatchPrintResult,
  IssueResult,
  MarkSignedResult,
  RequestCreate,
  RequestRead,
  SubmitResult,
} from "../model/types";

/** Создать заявку (черновик): POST /requests (teacher/worker). */
export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation<RequestRead, unknown, RequestCreate>({
    mutationFn: (body) => api.post<RequestRead>("/requests", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: requestKeys.all }),
  });
}

/** Подтвердить заявку (draft→to_issue): POST /requests/{id}/confirm (владелец). */
export function useConfirmRequest() {
  const qc = useQueryClient();
  return useMutation<RequestRead, unknown, number>({
    mutationFn: (id) => api.post<RequestRead>(`/requests/${id}/confirm`),
    onSuccess: () => qc.invalidateQueries({ queryKey: requestKeys.all }),
  });
}

/**
 * Выдать (to_issue→issued): POST /requests/{id}/issue (admin). СПИСАНИЕ со
 * склада происходит ИМЕННО ЗДЕСЬ (спека13 §2). Idempotency-Key гасит двойной
 * клик/ретрай сети до входа в транзакцию. Инвалидирует остатки, очередь и
 * счётчики карточек.
 */
export function useIssueRequest() {
  const qc = useQueryClient();
  return useMutation<IssueResult, unknown, number>({
    mutationFn: (id) =>
      api.post<IssueResult>(`/requests/${id}/issue`, undefined, {
        headers: { "Idempotency-Key": `issue-${id}-${crypto.randomUUID()}` },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: requestKeys.all });
      qc.invalidateQueries({ queryKey: ["stock"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

/**
 * Печать пачкой (спека13 §3): POST /requests/batch-print по выбранным issued-
 * заявкам. Создаёт пачку, ставит batch_id/printed_at, отдаёт batch_id для PDF.
 * Статус заявок НЕ меняет — только группирует и печатает.
 */
export function useBatchPrint() {
  const qc = useQueryClient();
  return useMutation<BatchPrintResult, unknown, number[]>({
    mutationFn: (ids) => api.post<BatchPrintResult>("/requests/batch-print", { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: requestKeys.all }),
  });
}

/**
 * Отметить подписанными пачкой (issued→signed): POST /requests/mark-signed
 * (спека13 §3). Работа только с исключениями — невыбранные (снятая галочка) в
 * список не попадают и остаются issued.
 */
export function useMarkSigned() {
  const qc = useQueryClient();
  return useMutation<MarkSignedResult, unknown, number[]>({
    mutationFn: (ids) => api.post<MarkSignedResult>("/requests/mark-signed", { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: requestKeys.all }),
  });
}

/**
 * Передать в бухгалтерию пачкой (signed→submitted): POST
 * /requests/submit-to-accounting (спека13 §4). Общий submitted_register_no на
 * весь вызов. Исключённые остаются signed.
 */
export function useSubmitToAccounting() {
  const qc = useQueryClient();
  return useMutation<SubmitResult, unknown, number[]>({
    mutationFn: (ids) => api.post<SubmitResult>("/requests/submit-to-accounting", { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: requestKeys.all }),
  });
}
