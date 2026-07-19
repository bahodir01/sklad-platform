import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import type { components } from "@/shared/api/schema";

export type TransferCreate = components["schemas"]["TransferCreate"];
export type TransferRead = components["schemas"]["TransferRead"];
export type TransferItemCreate = components["schemas"]["TransferItemCreate"];

/**
 * Провести перемещение: POST /transfers (admin, две записи ledger, SV-3).
 * Инвалидирует остатки и отчёты движений.
 */
export function useCreateTransfer() {
  const qc = useQueryClient();
  return useMutation<TransferRead, unknown, TransferCreate>({
    mutationFn: (body) => api.post<TransferRead>("/transfers", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stock"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}
