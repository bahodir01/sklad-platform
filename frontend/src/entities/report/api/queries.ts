import { useQuery } from "@tanstack/react-query";
import { api } from "@/shared/api/client";
import { reportKeys } from "@/shared/api/query-keys";
import type { Page } from "@/shared/api/types";
import type {
  BalanceReportRow,
  CashflowReport,
  MovementReportPage,
  UnpurchasedReportRow,
} from "../model/types";

type Q = Record<string, string | number | boolean | undefined>;

/** §8.1.1 Остатки: GET /reports/balances?format=json (admin). */
export function useBalancesReport(params: { page: number; size: number } & Q) {
  return useQuery<Page<BalanceReportRow>>({
    queryKey: reportKeys.balances(params),
    queryFn: () => api.get<Page<BalanceReportRow>>("/reports/balances", { format: "json", ...params }),
    placeholderData: (prev) => prev,
  });
}

/** §8.1.2 Недокупленное: GET /reports/unpurchased?format=json (admin). */
export function useUnpurchasedReport(params: { page: number; size: number } & Q) {
  return useQuery<Page<UnpurchasedReportRow>>({
    queryKey: reportKeys.unpurchased(params),
    queryFn: () =>
      api.get<Page<UnpurchasedReportRow>>("/reports/unpurchased", { format: "json", ...params }),
    placeholderData: (prev) => prev,
  });
}

/** §8.1.3 История движений: GET /reports/movements?format=json (keyset, admin). */
export function useMovementsReport(params: { limit: number; cursor?: string } & Q) {
  return useQuery<MovementReportPage>({
    queryKey: reportKeys.movements(params),
    queryFn: () => api.get<MovementReportPage>("/reports/movements", { format: "json", ...params }),
    placeholderData: (prev) => prev,
  });
}

/**
 * §8.2 ДДС: GET /reports/cashflow?category=...&format=json (admin). Фильтр по
 * категории ОБЯЗАТЕЛЕН (AP-8) — запрос идёт только когда category задана.
 */
export function useCashflowReport(
  params: { page: number; size: number; category?: string } & Q,
) {
  return useQuery<CashflowReport>({
    queryKey: reportKeys.cashflow(params),
    queryFn: () => api.get<CashflowReport>("/reports/cashflow", { format: "json", ...params }),
    enabled: !!params.category,
    placeholderData: (prev) => prev,
  });
}
