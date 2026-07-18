import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { isClientError } from "@/shared/api/errors";

/**
 * QueryClient с дефолтами §7.1:
 * - staleTime 5 мин: справочники меняются редко, дефолтный 0 рефетчит впустую;
 * - retry: 0 на 4xx (422/403 не изменятся), 2 на 5xx/сеть;
 * - refetchOnWindowFocus по умолчанию (со staleTime 5 мин стоит дёшево).
 * keepPreviousData задаётся на списках в useCatalogList, не глобально.
 */
function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5 * 60 * 1000,
        retry: (failureCount, error) => {
          if (isClientError(error)) return false;
          return failureCount < 2;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function QueryProvider({ children }: { children: ReactNode }) {
  // Один клиент на жизнь приложения (useState-инициализатор, не пересоздаётся).
  const [client] = useState(makeClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
