/**
 * Генерирует frontend/ui_manifest.json из дескрипторов entities/<x>/model/fields.ts
 * (§4, §8.7). Манифест НЕ пишется руками — иначе он разойдётся с UI и станет
 * проверять сам себя. Проверяется гейтом:
 *
 *   python .claude/skills/frontend-component-design/assets/ui_contract_validator.py \
 *          .feature-dev/02-contract.json  frontend/ui_manifest.json
 *
 * В манифесте `table` — имя таблицы КОНТРАКТА (expense_types), а не сегмент URL
 * (expense-types). Запуск: npm run ui:manifest.
 *
 * Примечание: fields.ts импортируют только `import type` — esbuild/tsx стирают
 * его, поэтому alias '@/...' в рантайме не резолвится и скрипт запускается.
 */
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import {
  listFieldNames,
  createFieldNames,
  updateFieldNames,
  type FieldDescriptor,
} from "../src/shared/lib/field-descriptor";
import { unitFields } from "../src/entities/unit/model/fields";
import { productFields } from "../src/entities/product/model/fields";
import { warehouseFields } from "../src/entities/warehouse/model/fields";
import { expenseTypeFields } from "../src/entities/expense-type/model/fields";
import { expenseCategoryFields } from "../src/entities/expense-category/model/fields";

interface View {
  name: string;
  table: string;
  kind: "list" | "detail" | "create" | "update";
  fields: string[];
}

/** Имена get_single-полей (для detail-вью), без id (table_view=false, но нужен ключ). */
function detailFieldNames(fields: FieldDescriptor[]): string[] {
  return fields.filter((f) => f.api.get_single && f.name !== "id").map((f) => f.name);
}

interface EntityCfg {
  /** имя таблицы КОНТРАКТА */
  table: string;
  fields: FieldDescriptor[];
  single: string;
  plural: string;
  /** есть ли отдельный экран/диалог детали (warehouses — да, из-за address) */
  detail?: boolean;
}

const ENTITIES: EntityCfg[] = [
  { table: "units", fields: unitFields, single: "Unit", plural: "Units" },
  { table: "products", fields: productFields, single: "Product", plural: "Products" },
  { table: "warehouses", fields: warehouseFields, single: "Warehouse", plural: "Warehouses", detail: true },
  { table: "expense_types", fields: expenseTypeFields, single: "ExpenseType", plural: "ExpenseTypes" },
  {
    table: "expense_categories",
    fields: expenseCategoryFields,
    single: "ExpenseCategory",
    plural: "ExpenseCategories",
  },
];

const views: View[] = [];
for (const e of ENTITIES) {
  views.push({ name: `${e.plural}Table`, table: e.table, kind: "list", fields: listFieldNames(e.fields) });
  if (e.detail) {
    views.push({ name: `${e.single}Detail`, table: e.table, kind: "detail", fields: detailFieldNames(e.fields) });
  }
  views.push({ name: `${e.single}CreateForm`, table: e.table, kind: "create", fields: createFieldNames(e.fields) });
  views.push({ name: `${e.single}EditForm`, table: e.table, kind: "update", fields: updateFieldNames(e.fields) });
}

const outPath = resolve(dirname(fileURLToPath(import.meta.url)), "..", "ui_manifest.json");
writeFileSync(outPath, JSON.stringify({ views }, null, 2) + "\n", "utf-8");
console.log(`ui_manifest.json записан: ${views.length} view(s) → ${outPath}`);
