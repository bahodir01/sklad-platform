import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { stockKeys } from "@/shared/api/query-keys";
import type { Page } from "@/shared/api/types";
import type { components } from "@/shared/api/schema";

export type StockBalance = components["schemas"]["StockBalanceList"];

/** Остатки по складам: GET /stock/balances (любая роль, AP-10). */
export function useStockBalances(
  params: { page: number; size: number; product_id?: number; warehouse_id?: number },
  enabled = true,
) {
  return useQuery<Page<StockBalance>>({
    queryKey: stockKeys.balances(params),
    queryFn: () => api.get<Page<StockBalance>>("/stock/balances", params),
    placeholderData: (prev) => prev,
    enabled,
  });
}
