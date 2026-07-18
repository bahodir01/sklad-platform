import type { FieldDescriptor } from "@/shared/lib/field-descriptor";

/**
 * expense_categories (расход ДЕНЕГ) — из 02-contract.json ДОСЛОВНО (§8.5).
 * Заголовок экрана — «Виды расхода денег». Контракт прямо предупреждает
 * «НЕ путать с expense_types (расход товара)».
 */
export const expenseCategoryFields: FieldDescriptor[] = [
  {
    name: "id",
    label: "ID",
    input_type: "number",
    required: false,
    disabled: true,
    table_view: false,
    api: { get_index: true, get_single: true, create: false, update: false },
  },
  {
    name: "name",
    label: "Вид расхода денег",
    input_type: "text",
    required: true,
    max: 100,
    table_view: true,
    api: { get_index: true, get_single: true, create: true, update: true },
  },
  {
    name: "status",
    label: "Статус",
    input_type: "select",
    required: false,
    table_view: true,
    api: { get_index: true, get_single: true, create: false, update: true },
  },
];
