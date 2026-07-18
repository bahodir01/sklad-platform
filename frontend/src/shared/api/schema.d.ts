/**
 * Типы API — форма `openapi-typescript` (components['schemas'][...]).
 *
 * ВРЕМЕННО написан руками СТРОГО по backend-схемам этапа 1
 * (backend/app/modules/{auth,catalog}/schemas.py) и по 02-contract.json.
 * Как только бэкенд отдаёт /openapi.json — заменяется командой:
 *
 *     npm run api:types
 *
 * После генерации файл коммитится; расхождение с бэком = падение сборки
 * (архитектура §2). Ручных `interface Unit {...}` в проекте быть не должно —
 * все доменные типы выводятся из этого файла (см. entities/<x>/model/types.ts).
 */

export type UserRole = "admin" | "teacher" | "worker";
export type UserCategory = "teacher" | "worker";
export type CatalogStatus = "active" | "archived";

export interface components {
  schemas: {
    // ── auth / users ────────────────────────────────────────────────
    LoginRequest: {
      /** @minLength 1 @maxLength 150 */
      username: string;
      /** @minLength 1 @maxLength 128 */
      password: string;
    };
    TokenResponse: {
      access_token: string;
      /** @default "bearer" */
      token_type: string;
      expires_in: number;
    };
    UserRead: {
      id: number;
      full_name: string;
      username: string;
      role: UserRole;
      category: UserCategory | null;
      is_active: boolean;
      /** @format date-time */
      created_at: string;
    };

    // ── units ───────────────────────────────────────────────────────
    UnitList: {
      id: number;
      code: string;
      name: string;
      is_active: boolean;
    };
    UnitRead: components["schemas"]["UnitList"];
    UnitCreate: {
      /** @minLength 1 @maxLength 16 */
      code: string;
      /** @minLength 1 @maxLength 100 */
      name: string;
    };
    UnitUpdate: {
      /** @minLength 1 @maxLength 16 */
      code?: string | null;
      /** @minLength 1 @maxLength 100 */
      name?: string | null;
      is_active?: boolean | null;
    };

    // ── products ────────────────────────────────────────────────────
    ProductList: {
      id: number;
      name: string;
      unit_id: number;
      sku: string | null;
      status: CatalogStatus;
    };
    ProductRead: components["schemas"]["ProductList"];
    ProductCreate: {
      /** @minLength 1 @maxLength 255 */
      name: string;
      unit_id: number;
      /** @maxLength 64 */
      sku?: string | null;
    };
    ProductUpdate: {
      /** @minLength 1 @maxLength 255 */
      name?: string | null;
      /** @maxLength 64 */
      sku?: string | null;
      status?: CatalogStatus | null;
    };

    // ── warehouses ──────────────────────────────────────────────────
    WarehouseList: {
      id: number;
      code: string;
      name: string;
      allows_issuance: boolean;
      status: CatalogStatus;
    };
    WarehouseRead: {
      id: number;
      code: string;
      name: string;
      address: string | null;
      allows_issuance: boolean;
      status: CatalogStatus;
    };
    WarehouseCreate: {
      /** @minLength 1 @maxLength 32 */
      code: string;
      /** @minLength 1 @maxLength 255 */
      name: string;
      /** @maxLength 500 */
      address?: string | null;
      /** @default false */
      allows_issuance?: boolean;
    };
    WarehouseUpdate: {
      /** @minLength 1 @maxLength 32 */
      code?: string | null;
      /** @minLength 1 @maxLength 255 */
      name?: string | null;
      /** @maxLength 500 */
      address?: string | null;
      allows_issuance?: boolean | null;
      status?: CatalogStatus | null;
    };

    // ── expense_types (расход ТОВАРА) ───────────────────────────────
    ExpenseTypeList: {
      id: number;
      name: string;
      requires_employee: boolean;
      status: CatalogStatus;
    };
    ExpenseTypeRead: components["schemas"]["ExpenseTypeList"];
    ExpenseTypeCreate: {
      /** @minLength 1 @maxLength 100 */
      name: string;
      requires_employee: boolean;
    };
    ExpenseTypeUpdate: {
      /** @minLength 1 @maxLength 100 */
      name?: string | null;
      requires_employee?: boolean | null;
      status?: CatalogStatus | null;
    };

    // ── expense_categories (расход ДЕНЕГ) ───────────────────────────
    ExpenseCategoryList: {
      id: number;
      name: string;
      status: CatalogStatus;
    };
    ExpenseCategoryRead: components["schemas"]["ExpenseCategoryList"];
    ExpenseCategoryCreate: {
      /** @minLength 1 @maxLength 100 */
      name: string;
    };
    ExpenseCategoryUpdate: {
      /** @minLength 1 @maxLength 100 */
      name?: string | null;
      status?: CatalogStatus | null;
    };

    // ── конверт ошибки {code, message, details} (core/exceptions.py) ─
    ErrorEnvelope: {
      code: string;
      message: string;
      details: Record<string, unknown>;
    };
  };
}

export type Schemas = components["schemas"];
