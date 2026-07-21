/**
 * Удобные псевдонимы enum-типов контракта. `openapi-typescript` (плоский вывод)
 * НЕ создаёт корневых `export type UserRole = ...`, а только `components`; эти
 * алиасы держим здесь руками, чтобы `npm run api:types` их не затирал при
 * перегенерации schema.d.ts. Значение — то же самое место в схеме.
 */
import type { components } from "./schema";

export type UserRole = components["schemas"]["UserRole"];
export type UserCategory = components["schemas"]["UserCategory"];
export type CatalogStatus = components["schemas"]["CatalogStatus"];
