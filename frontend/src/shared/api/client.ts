/**
 * Единый HTTP-клиент (§10).
 *
 * base /api/v1 · credentials:'include' · Authorization: Bearer из tokenStore ·
 * разбор {code,message,details} в ApiError · single-flight refresh на 401.
 * Живёт вне React и читает токен синхронно.
 */

import { API_BASE } from "./config";
import { ApiError } from "./errors";
import { handleAuthLost, refreshAccessToken } from "./refresh";
import { tokenStore } from "./token-store";
import type { ErrorEnvelope } from "./types";

export type QueryValue = string | number | boolean | null | undefined;

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  query?: Record<string, QueryValue>;
  body?: unknown;
  /** true для /auth/login и /auth/refresh — иначе ретрай-рекурсия по 401. */
  skipAuthRetry?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  // ВАЖНО (память проекта): без завершающего слэша — Vercel/прокси [...path]
  // на URL со слэшем в конце отдаёт NOT_FOUND.
  let url = `${API_BASE}${path}`;
  if (query) {
    const usp = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") {
        usp.append(key, String(value));
      }
    }
    const qs = usp.toString();
    if (qs) url += `?${qs}`;
  }
  return url;
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as ErrorEnvelope;
    if (body && typeof body.message === "string" && typeof body.code === "string") {
      return new ApiError(res.status, body);
    }
    return new ApiError(res.status, {
      code: "http_error",
      message: `Ошибка сервера (${res.status})`,
      details: {},
    });
  } catch {
    return new ApiError(res.status, {
      code: "http_error",
      message: `Ошибка сервера (${res.status})`,
      details: {},
    });
  }
}

async function rawFetch(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let bodyInit: BodyInit | undefined;
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    bodyInit = JSON.stringify(options.body);
  }

  return fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body: bodyInit,
    credentials: "include",
    signal: options.signal,
  });
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let res: Response;
  try {
    res = await rawFetch(path, options);
  } catch {
    throw ApiError.network();
  }

  // 401 → single-flight refresh → один повтор. Кроме самих auth-эндпоинтов.
  if (res.status === 401 && !options.skipAuthRetry) {
    const ok = await refreshAccessToken();
    if (ok) {
      try {
        res = await rawFetch(path, options);
      } catch {
        throw ApiError.network();
      }
    } else {
      handleAuthLost();
      throw await parseError(res);
    }
  }

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    throw await parseError(res);
  }

  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>, signal?: AbortSignal) =>
    request<T>(path, { method: "GET", query, signal }),
  post: <T>(path: string, body?: unknown, opts?: Partial<RequestOptions>) =>
    request<T>(path, { method: "POST", body, ...opts }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
};
