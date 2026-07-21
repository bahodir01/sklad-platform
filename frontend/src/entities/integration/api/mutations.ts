import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { integrationKeys } from "@/shared/api/query-keys";
import type { Integration, IntegrationKind } from "../model/types";

/**
 * Сохранить и проверить секрет: PUT /admin/integrations/{kind} (admin,
 * спека15 §5а). Сервер проверяет секрет ДО сохранения (Telegram `getMe` /
 * формат ai_search-ключа) — невалидный секрет вернёт 422 с готовым текстом
 * ошибки (в т.ч. дословно от Telegram) и НЕ сохранится.
 */
export function useUpdateIntegration() {
  const qc = useQueryClient();
  return useMutation<Integration, unknown, { kind: IntegrationKind; secret: string }>({
    mutationFn: ({ kind, secret }) =>
      api.put<Integration>(`/admin/integrations/${kind}`, { secret }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: integrationKeys.all });
    },
  });
}

/** Отключить интеграцию: POST /admin/integrations/{kind}/disable (admin). */
export function useDisableIntegration() {
  const qc = useQueryClient();
  return useMutation<Integration, unknown, { kind: IntegrationKind }>({
    mutationFn: ({ kind }) => api.post<Integration>(`/admin/integrations/${kind}/disable`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: integrationKeys.all });
    },
  });
}
