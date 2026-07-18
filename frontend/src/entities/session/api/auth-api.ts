import { request } from "@/shared/api/client";
import type { components } from "@/shared/api/schema";

type LoginRequest = components["schemas"]["LoginRequest"];
type TokenResponse = components["schemas"]["TokenResponse"];
type UserRead = components["schemas"]["UserRead"];

/**
 * Сырые вызовы auth (§10). refresh здесь НЕ дублируется — он в shared/api/refresh
 * (single-flight). login/logout помечены skipAuthRetry: на 401 их нельзя гонять
 * через refresh (рекурсия).
 */

export function login(payload: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: payload,
    skipAuthRetry: true,
  });
}

export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST", skipAuthRetry: true });
}

export function fetchMe(signal?: AbortSignal): Promise<UserRead> {
  return request<UserRead>("/auth/me", { method: "GET", signal });
}
