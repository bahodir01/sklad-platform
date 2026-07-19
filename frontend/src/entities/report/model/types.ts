/**
 * М6 Отчёты. Эндпоинты объявлены `response_model=None` (роутер отдаёт json ИЛИ
 * файл по ?format=), поэтому их строки НЕ попадают в OpenAPI и типов в
 * schema.d.ts для них нет. Здесь — ручная проекция reports/schemas.py ДОСЛОВНО
 * (это транспортные JOIN-проекции, не таблицы контракта — суффиксов
 * Create/Update/Read/List у них намеренно нет). Decimal приходит строкой.
 */

import type { components } from "@/shared/api/schema";

export type MovementDocType = components["schemas"]["MovementDocType"];
export type UserCategory = "teacher" | "worker";
export type CashDeskType = components["schemas"]["CashDeskType"];

/** §8.1.1 Остатки в реальном времени (AP-10). */
export interface BalanceReportRow {
  product_id: number;
  product_name: string;
  sku: string | null;
  unit_id: number;
  unit_code: string;
  warehouse_id: number;
  warehouse_code: string;
  warehouse_name: string;
  qty: string;
}

/** §8.1.2 Недокупленное по уведомлениям (AP-6). */
export interface UnpurchasedReportRow {
  notification_id: number;
  notification_number: string;
  notification_date: string;
  product_id: number;
  product_name: string;
  unit_code: string;
  qty_requested: string;
  qty_purchased: string;
  qty_remaining: string;
}

/** §8.1.3 История движений (AP-5, keyset). */
export interface MovementReportRow {
  id: number;
  created_at: string;
  product_id: number;
  product_name: string;
  unit_code: string;
  warehouse_id: number;
  warehouse_code: string;
  qty: string;
  doc_type: MovementDocType;
  doc_type_label: string;
  doc_id: number;
}

export interface MovementReportPage {
  items: MovementReportRow[];
  next_cursor: string | null;
  limit: number;
}

/** §8.2 ДДС (AP-8). */
export interface CashflowReportRow {
  id: number;
  date: string;
  employee_id: number;
  employee_name: string;
  employee_category: UserCategory | null;
  cash_desk_id: number;
  cash_desk_type: CashDeskType;
  expense_category_id: number;
  expense_category_name: string;
  amount: string;
  description: string;
  receipt_object: string;
  receipt_url: string | null;
}

export interface CashDeskBalance {
  cash_desk_id: number;
  cash_desk_type: CashDeskType;
  balance: string;
}

export interface CashflowSummary {
  category: UserCategory;
  date_from: string | null;
  date_to: string | null;
  total_income: string;
  total_expense: string;
  net: string;
  desk_balances: CashDeskBalance[];
}

export interface CashflowReport {
  items: CashflowReportRow[];
  total: number;
  page: number;
  size: number;
  pages: number;
  summary: CashflowSummary;
}

/** Русские подписи вида документа движения (дублирует doc_type_label с бэка). */
export const MOVEMENT_DOC_LABEL: Record<MovementDocType, string> = {
  acquisition: "Приобретение",
  transfer: "Перемещение",
  writeoff: "Расход",
};
