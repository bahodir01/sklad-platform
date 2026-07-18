/**
 * Хранилище access-токена (§6, ТЗ §7).
 *
 * Access живёт ТОЛЬКО в этом модульном синглтоне — в памяти JS. НЕ в Zustand,
 * НЕ в localStorage/sessionStorage: это XSS-кража токена. Синглтон физически
 * нечем сериализовать — в этом его защита. `client.ts` читает токен синхронно,
 * вне React, без подписки на стор.
 *
 * (entities/session/model/token-store.ts реэкспортирует это под именем из
 * архитектуры; низкий уровень лежит в shared, чтобы client.ts не импортировал
 * вверх по слоям FSD.)
 */

let accessToken: string | null = null;

export const tokenStore = {
  get(): string | null {
    return accessToken;
  },
  set(token: string): void {
    accessToken = token;
  },
  clear(): void {
    accessToken = null;
  },
};
