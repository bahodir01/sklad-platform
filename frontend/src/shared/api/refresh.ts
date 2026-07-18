/**
 * Single-flight обновление access-токена по refresh-cookie (§6).
 *
 * При 401 первый запрос дёргает /auth/refresh, остальные встают в очередь на
 * тот же промис и после успеха повторяются ОДИН раз. Наивная реализация дала бы
 * три параллельных refresh (таблица + /auth/me + селект), а ротация с детекцией
 * переиспользования (backend Б-1) погасила бы всю семью токенов и выкинула
 * пользователя. Поэтому промис ровно один.
 */

import { API_BASE } from "./config";
import { tokenStore } from "./token-store";
import type { components } from "./schema";

type TokenResponse = components["schemas"]["TokenResponse"];

let inflight: Promise<boolean> | null = null;

/** Колбэк «сессия потеряна» — регистрируется entities/session вне слоя shared. */
let onAuthLost: (() => void) | null = null;

export function registerAuthLostHandler(handler: () => void): void {
  onAuthLost = handler;
}

async function doRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) {
      tokenStore.clear();
      return false;
    }
    const data = (await res.json()) as TokenResponse;
    tokenStore.set(data.access_token);
    return true;
  } catch {
    tokenStore.clear();
    return false;
  }
}

/**
 * Обновляет токен, коллапсируя параллельные вызовы в один промис.
 * true — токен обновлён; false — refresh отклонён (сессии нет).
 */
export function refreshAccessToken(): Promise<boolean> {
  if (!inflight) {
    inflight = doRefresh().finally(() => {
      inflight = null;
    });
  }
  return inflight;
}

/** Вызывается при окончательном провале авторизации: чистка + сигнал в UI. */
export function handleAuthLost(): void {
  tokenStore.clear();
  onAuthLost?.();
}
