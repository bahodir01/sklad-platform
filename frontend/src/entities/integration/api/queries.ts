import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { integrationKeys } from "@/shared/api/query-keys";
import type { Integration } from "../model/types";

/** Список интеграций: GET /admin/integrations (admin, спека15 §5а). */
export function useIntegrations() {
  return useQuery<Integration[]>({
    queryKey: integrationKeys.all,
    queryFn: () => api.get<Integration[]>("/admin/integrations"),
  });
}
