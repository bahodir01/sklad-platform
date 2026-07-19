import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { WriteoffCreate, WriteoffRead } from "../model/types";

/**
 * Прямое списание порча/брак: POST /writeoffs (admin, §4.4). Только типы с
 * requires_employee=false — сотрудник НЕ указывается, списывает немедленно
 * (ledger.post(−qty), без статусов и печати). Инвалидирует остатки и отчёты
 * движений. Ошибку недостатка остатка (InsufficientStock) и попытку выбрать
 * «Выдача»-тип отклоняет сервер — его сообщение выводит вызывающий тостером.
 */
export function useCreateWriteoff() {
  const qc = useQueryClient();
  return useMutation<WriteoffRead, unknown, WriteoffCreate>({
    mutationFn: (body) => api.post<WriteoffRead>("/writeoffs", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stock"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}
