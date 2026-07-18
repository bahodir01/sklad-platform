import type { components } from "./schema";

/** Все доменные типы выводятся из schema.d.ts — руками не объявлять (§2). */
export type Schemas = components["schemas"];

/** Конверт списка бэкенда {items, total, page, size, pages} (shared/pagination.py). */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/** Конверт ошибки {code, message, details} (core/exceptions.py). */
export interface ErrorEnvelope {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

/**
 * Ошибки валидации Pydantic внутри details.errors: {loc, type, msg}.
 * loc[последний сегмент] = имя атрибута контракта → на него кладём setError.
 */
export interface FieldValidationError {
  loc: string[];
  type: string;
  msg: string;
}

/** Общие параметры списка. */
export interface PageParams {
  page: number;
  size: number;
}
