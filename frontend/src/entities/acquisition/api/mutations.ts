import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { documentKeys } from "@/shared/api/query-keys";
import type { components } from "@/shared/api/schema";

export type AcquisitionCreate = components["schemas"]["AcquisitionCreate"];
export type AcquisitionRead = components["schemas"]["AcquisitionRead"];
export type AcquisitionItemCreate = components["schemas"]["AcquisitionItemCreate"];

/**
 * Провести приобретение: POST /acquisitions (admin, SV-1 контроль перезакупки).
 * Инвалидирует уведомления (остаток к приобретению пересчитывается), остатки и
 * отчёты. Ошибку перезакупки §4.2 выводит вызывающий тостером.
 */
export function useCreateAcquisition() {
  const qc = useQueryClient();
  return useMutation<AcquisitionRead, unknown, AcquisitionCreate>({
    mutationFn: (body) => api.post<AcquisitionRead>("/acquisitions", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: documentKeys.notifications.all });
      qc.invalidateQueries({ queryKey: ["stock"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}
